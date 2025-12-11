from flask import current_app as app
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash


class User:
    def __init__(self, id, email, full_name, address, created_at):
        self.id = id
        self.email = email
        self.full_name = full_name
        self.address = address
        self.created_at = created_at

    @property
    def firstname(self):
        if not self.full_name:
            return ''
        return self.full_name.split()[0]

    @staticmethod
    def get_with_password(email):
        rows = app.db.execute(
            """
SELECT id, email, full_name, address, created_at, password_hash
FROM Users
WHERE email = :email
""",
            email=email,
        )
        if not rows:
            return None
        row = rows[0]
        user = User(row[0], row[1], row[2], row[3], row[4])
        password_hash = row[5]
        return user, password_hash

    @staticmethod
    def email_exists(email, exclude_user_id=None):
        query = """
SELECT 1
FROM Users
WHERE email = :email
"""
        params = {'email': email}
        if exclude_user_id is not None:
            query += " AND id <> :exclude_user_id"
            params['exclude_user_id'] = exclude_user_id

        rows = app.db.execute(query, **params)
        return len(rows) > 0

    @staticmethod
    def create(email, full_name, address, password_plaintext):
        rows = app.db.execute(
            """
INSERT INTO Users (email, full_name, address, password_hash)
VALUES (:email, :full_name, :address, :password_hash)
RETURNING id
""",
            email=email,
            full_name=full_name,
            address=address,
            password_hash=generate_password_hash(password_plaintext),
        )
        return User.get(rows[0][0]) if rows else None

    @staticmethod
    def update_profile(user_id, full_name, address, email=None):
        params = {
            'full_name': full_name,
            'address': address,
            'user_id': user_id,
        }
        email_clause = ''
        if email is not None:
            email_clause = ", email = :email"
            params['email'] = email

        rows = app.db.execute(
            f"""
UPDATE Users
SET full_name = :full_name,
    address = :address{email_clause}
WHERE id = :user_id
RETURNING id
""",
            **params,
        )
        return len(rows) == 1

    @staticmethod
    def get(id):
        rows = app.db.execute(
            """
SELECT id, email, full_name, address, created_at
FROM Users
WHERE id = :id
""",
            id=id,
        )
        return User(*rows[0]) if rows else None

    @staticmethod
    def authenticate(email, password_plaintext):
        result = User.get_with_password(email)
        if not result:
            return None
        user, password_hash = result
        if not check_password_hash(password_hash, password_plaintext):
            return None
        return user

    @staticmethod
    def update_password(user_id, new_password_plaintext):
        rows = app.db.execute(
            """
UPDATE Users
SET password_hash = :password_hash
WHERE id = :user_id
RETURNING id
""",
            password_hash=generate_password_hash(new_password_plaintext),
            user_id=user_id,
        )
        return len(rows) == 1

    @staticmethod
    def get_balance(user_id):
        rows = app.db.execute(
            """
SELECT balance_cents
FROM account_balance
WHERE user_id = :user_id
""",
            user_id=user_id,
        )
        return rows[0][0] if rows else 0

    @staticmethod
    def adjust_balance(user_id, delta_cents, note=None):
        if delta_cents == 0:
            return User.get_balance(user_id)

        with app.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
INSERT INTO account_balance (user_id, balance_cents)
VALUES (:user_id, 0)
ON CONFLICT (user_id) DO NOTHING
"""
                ),
                {'user_id': user_id},
            )

            balance_row = conn.execute(
                text(
                    """
SELECT balance_cents
FROM account_balance
WHERE user_id = :user_id
FOR UPDATE
"""
                ),
                {'user_id': user_id},
            ).first()

            current_balance = balance_row[0] if balance_row else 0
            new_balance = current_balance + delta_cents
            if new_balance < 0:
                raise ValueError('Insufficient funds')

            conn.execute(
                text(
                    """
UPDATE account_balance
SET balance_cents = :new_balance
WHERE user_id = :user_id
"""
                ),
                {'new_balance': new_balance, 'user_id': user_id},
            )
            conn.execute(
                text(
                    """
INSERT INTO balance_tx (user_id, amount_cents, note)
VALUES (:user_id, :amount_cents, :note)
"""
                ),
                {
                    'user_id': user_id,
                    'amount_cents': delta_cents,
                    'note': note or '',
                },
            )

        return new_balance

    @staticmethod
    def get_balance_history(user_id):
        rows = app.db.execute(
            """
SELECT created_at, amount_cents, note
FROM balance_tx
WHERE user_id = :user_id
ORDER BY created_at DESC
""",
            user_id=user_id,
        )
        return [
            {
                'created_at': row[0],
                'amount_cents': row[1],
                'note': row[2],
            }
            for row in rows
        ]
