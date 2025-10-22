from flask import current_app as app
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash


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
    def email_exists(email):
        rows = app.db.execute(
            """
SELECT 1
FROM Users
WHERE email = :email
""",
            email=email,
        )
        return len(rows) > 0

    @staticmethod
    def create(email, full_name, address, password):
        rows = app.db.execute(
            """
INSERT INTO Users (email, full_name, address, password_hash)
VALUES (:email, :full_name, :address, :password_hash)
RETURNING id
""",
            email=email,
            full_name=full_name,
            address=address,
            password_hash=generate_password_hash(password),
        )
        return User.get(rows[0][0]) if rows else None

    @staticmethod
    def update_profile(user_id, email, full_name, address):
        rows = app.db.execute(
            """
UPDATE Users
SET email = :email,
    full_name = :full_name,
    address = :address
WHERE id = :user_id
RETURNING id
""",
            email=email,
            full_name=full_name,
            address=address,
            user_id=user_id,
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
    def authenticate(email, password):
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
        if not check_password_hash(row[5], password):
            return None
        return User(row[0], row[1], row[2], row[3], row[4])
