from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash


bp = Blueprint('account', __name__)


def _row_to_user(row):
    if not row:
        return None
    return {
        'id': row[0],
        'email': row[1],
        'full_name': row[2],
        'address': row[3],
        'created_at': row[4],
    }


def _load_user(user_id):
    rows = current_app.db.execute(
        """
        SELECT id, email, full_name, address, created_at
        FROM users
        WHERE id = :uid
        """,
        uid=user_id,
    )
    return _row_to_user(rows[0]) if rows else None


def _load_user_with_password(email):
    rows = current_app.db.execute(
        """
        SELECT id, email, full_name, address, created_at, password_hash
        FROM users
        WHERE email = :email
        """,
        email=email,
    )
    if not rows:
        return None
    row = rows[0]
    user = _row_to_user(row[:5])
    password_hash = row[5]
    return user, password_hash


@bp.before_app_request
def attach_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = _load_user(user_id)
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('account.login', next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _format_money(cents):
    try:
        return f"${cents / 100:.2f}"
    except (TypeError, ValueError):
        return "$0.00"


@bp.app_context_processor
def inject_helpers():
    return {'format_money': _format_money}


def _parse_amount(raw_value):
    try:
        amount = Decimal(raw_value)
    except (InvalidOperation, TypeError):
        return None
    cents = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return cents


def _ensure_balance_row(conn, user_id):
    conn.execute(
        text(
            """
            INSERT INTO account_balance (user_id, balance_cents)
            VALUES (:uid, 0)
            ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {'uid': user_id},
    )


def _get_balance(user_id):
    rows = current_app.db.execute(
        """
        SELECT balance_cents
        FROM account_balance
        WHERE user_id = :uid
        """,
        uid=user_id,
    )
    return rows[0][0] if rows else 0


def _get_orders_for_user(user_id):
    rows = current_app.db.execute(
        """
        SELECT o.id,
               o.created_at,
               o.total_cents,
               o.fulfilled,
               oi.id AS order_item_id,
               oi.quantity,
               oi.unit_price_cents,
               oi.fulfilled_at,
               p.name AS product_name
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE o.buyer_id = :uid
        ORDER BY o.created_at DESC, oi.id
        """,
        uid=user_id,
    )
    orders = []
    order_lookup = {}
    for row in rows:
        order_id = row[0]
        if order_id not in order_lookup:
            order_lookup[order_id] = {
                'id': order_id,
                'created_at': row[1],
                'total_cents': row[2],
                'fulfilled': row[3],
                'items': [],
            }
            orders.append(order_lookup[order_id])

        item_id = row[4]
        if item_id is not None:
            order_lookup[order_id]['items'].append(
                {
                    'order_item_id': item_id,
                    'product_name': row[8],
                    'unit_price_cents': row[6],
                    'quantity': row[5],
                    'fulfilled_at': row[7],
                }
            )

    for order in orders:
        order['item_count'] = len(order['items'])

    return orders


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect(url_for('account.account_home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        address = request.form.get('address', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        errors = []
        if not email:
            errors.append('Email is required.')
        if not full_name:
            errors.append('Full name is required.')
        if not address:
            errors.append('Address is required.')
        if not password:
            errors.append('Password is required.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template(
                'account/register.html',
                email=email,
                full_name=full_name,
                address=address,
            )

        try:
            with current_app.db.engine.begin() as conn:
                new_user = conn.execute(
                    text(
                        """
                        INSERT INTO users (email, full_name, address, password_hash)
                        VALUES (:email, :full_name, :address, :password_hash)
                        RETURNING id
                        """
                    ),
                    {
                        'email': email,
                        'full_name': full_name,
                        'address': address,
                        'password_hash': generate_password_hash(password),
                    },
                ).first()
                user_id = new_user[0]
                _ensure_balance_row(conn, user_id)
        except IntegrityError:
            flash('Email is already registered.', 'error')
            return render_template(
                'account/register.html',
                email=email,
                full_name=full_name,
                address=address,
            )

        session.clear()
        session['user_id'] = user_id
        flash('Welcome! Your account has been created.', 'success')
        return redirect(url_for('account.account_home'))

    return render_template('account/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('account.account_home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('account/login.html', email=email)

        result = _load_user_with_password(email)
        if not result:
            flash('Invalid email or password.', 'error')
            return render_template('account/login.html', email=email)

        user, password_hash = result
        if not check_password_hash(password_hash, password):
            flash('Invalid email or password.', 'error')
            return render_template('account/login.html', email=email)

        session.clear()
        session['user_id'] = user['id']
        flash('Logged in successfully.', 'success')
        next_url = request.args.get('next')
        return redirect(next_url or url_for('account.account_home'))

    return render_template('account/login.html')


@bp.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index.index'))


@bp.route('/account')
@login_required
def account_home():
    balance_cents = _get_balance(g.user['id'])
    return render_template(
        'account/account.html',
        user=g.user,
        balance_cents=balance_cents,
    )


@bp.route('/account/edit', methods=['GET', 'POST'])
@login_required
def account_edit():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        address = request.form.get('address', '').strip()

        errors = []
        if not email:
            errors.append('Email is required.')
        if not full_name:
            errors.append('Full name is required.')
        if not address:
            errors.append('Address is required.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template(
                'account/account_edit.html',
                user={
                    'email': email or g.user['email'],
                    'full_name': full_name or g.user['full_name'],
                    'address': address or g.user['address'],
                },
            )

        try:
            with current_app.db.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE users
                        SET email = :email,
                            full_name = :full_name,
                            address = :address
                        WHERE id = :uid
                        """
                    ),
                    {
                        'email': email,
                        'full_name': full_name,
                        'address': address,
                        'uid': g.user['id'],
                    },
                )
        except IntegrityError:
            flash('Email is already registered.', 'error')
            return render_template(
                'account/account_edit.html',
                user={
                    'email': email,
                    'full_name': full_name,
                    'address': address,
                },
            )

        session['user_id'] = g.user['id']
        flash('Account updated.', 'success')
        return redirect(url_for('account.account_home'))

    return render_template('account/account_edit.html', user=g.user)


@bp.route('/account/deposit', methods=['POST'])
@login_required
def account_deposit():
    amount_raw = request.form.get('amount', '').strip()
    amount_cents = _parse_amount(amount_raw)
    if amount_cents is None or amount_cents <= 0:
        flash('Enter a positive deposit amount.', 'error')
        return redirect(url_for('account.account_home'))

    with current_app.db.engine.begin() as conn:
        _ensure_balance_row(conn, g.user['id'])
        conn.execute(
            text(
                """
                UPDATE account_balance
                SET balance_cents = balance_cents + :amount
                WHERE user_id = :uid
                """
            ),
            {'amount': amount_cents, 'uid': g.user['id']},
        )
        conn.execute(
            text(
                """
                INSERT INTO balance_tx (user_id, amount_cents, note)
                VALUES (:uid, :amount, 'manual deposit')
                """
            ),
            {'uid': g.user['id'], 'amount': amount_cents},
        )

    flash('Deposit recorded.', 'success')
    return redirect(url_for('account.account_home'))


@bp.route('/account/withdraw', methods=['POST'])
@login_required
def account_withdraw():
    amount_raw = request.form.get('amount', '').strip()
    amount_cents = _parse_amount(amount_raw)
    if amount_cents is None or amount_cents <= 0:
        flash('Enter a positive withdrawal amount.', 'error')
        return redirect(url_for('account.account_home'))

    balance_cents = _get_balance(g.user['id'])
    if amount_cents > balance_cents:
        flash('Withdrawal exceeds available balance.', 'error')
        return redirect(url_for('account.account_home'))

    with current_app.db.engine.begin() as conn:
        _ensure_balance_row(conn, g.user['id'])
        conn.execute(
            text(
                """
                UPDATE account_balance
                SET balance_cents = balance_cents - :amount
                WHERE user_id = :uid
                """
            ),
            {'amount': amount_cents, 'uid': g.user['id']},
        )
        conn.execute(
            text(
                """
                INSERT INTO balance_tx (user_id, amount_cents, note)
                VALUES (:uid, :amount, 'manual withdraw')
                """
            ),
            {'uid': g.user['id'], 'amount': -amount_cents},
        )

    flash('Withdrawal recorded.', 'success')
    return redirect(url_for('account.account_home'))


@bp.route('/account/purchases')
@login_required
def account_purchases():
    orders = _get_orders_for_user(g.user['id'])
    return render_template('account/purchases.html', orders=orders)


@bp.route('/account/purchase_lookup')
@login_required
def account_purchase_lookup():
    return render_template('account/purchase_lookup.html')


@bp.route('/api/users/<int:user_id>/purchases')
def api_user_purchases(user_id):
    orders = _get_orders_for_user(user_id)
    results = []
    for order in orders:
        created_at = order['created_at']
        formatted_items = []
        for item in order['items']:
            fulfilled_at = item['fulfilled_at']
            formatted_items.append(
                {
                    'order_item_id': item['order_item_id'],
                    'product_name': item['product_name'],
                    'unit_price_cents': item['unit_price_cents'],
                    'quantity': item['quantity'],
                    'fulfilled_at': fulfilled_at.isoformat() if hasattr(fulfilled_at, 'isoformat') and fulfilled_at else fulfilled_at,
                    'line_total_cents': (item['unit_price_cents'] or 0) * (item['quantity'] or 0),
                }
            )
        results.append(
            {
                'id': order['id'],
                'created_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
                'total_cents': order['total_cents'],
                'fulfilled': bool(order['fulfilled']),
                'item_count': order['item_count'],
                'items': formatted_items,
            }
        )
    return jsonify({'orders': results})


@bp.route('/u/<int:user_id>')
def public_profile(user_id):
    user = _load_user(user_id)
    if not user:
        abort(404)

    seller_rows = current_app.db.execute(
        """
        SELECT 1
        FROM order_items
        WHERE seller_id = :uid
        LIMIT 1
        """,
        uid=user_id,
    )
    is_seller = bool(seller_rows)
    return render_template('account/public_profile.html', user=user, is_seller=is_seller)
