from functools import wraps
import math

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

from app.models import purchases
from app.models.user import User
from app.models import seller_review


bp = Blueprint('account', __name__)
PURCHASES_PAGE_SIZE = 10


@bp.before_app_request
def attach_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
        return

    user = User.get(user_id)
    if user is None:
        session.clear()
        g.user = None
        return

    g.user = user


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


def _parse_positive_int(raw_value, default, minimum=1, maximum=None):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _serialize_datetime(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _serialize_order(order):
    return {
        'order_id': order['order_id'],
        'order_created_at': _serialize_datetime(order['order_created_at']),
        'total_cents': order['total_cents'],
        'item_count': order['item_count'],
        'all_fulfilled': order['all_fulfilled'],
        'items': [
            {
                'product_id': item['product_id'],
                'product_name': item['product_name'],
                'quantity': item['quantity'],
                'unit_price_cents': item['unit_price_cents'],
                'line_total_cents': item['line_total_cents'],
                'fulfilled': item['fulfilled'],
            }
            for item in order.get('items', [])
        ],
    }


def _get_order_detail(order_id):
    header_rows = current_app.db.execute(
        """
SELECT
    o.id,
    o.buyer_id,
    o.created_at,
    o.fulfilled,
    o.total_cents,
    u.full_name,
    u.address,
    u.email
FROM orders o
LEFT JOIN users u ON u.id = o.buyer_id
WHERE o.id = :order_id
""",
        order_id=order_id,
    )
    if not header_rows:
        return None

    header = header_rows[0]
    line_rows = current_app.db.execute(
        """
SELECT
    oi.id,
    oi.product_id,
    p.name,
    oi.seller_id,
    oi.quantity,
    oi.unit_price_cents,
    oi.fulfilled_at
FROM order_items oi
JOIN products p ON p.id = oi.product_id
WHERE oi.order_id = :order_id
ORDER BY oi.id
""",
        order_id=order_id,
    )

    computed_total = 0
    line_items = []
    for row in line_rows:
        quantity = row[4] or 0
        unit_price = row[5] or 0
        line_total = quantity * unit_price
        computed_total += line_total
        line_items.append(
            {
                'order_item_id': row[0],
                'product_id': row[1],
                'product_name': row[2],
                'seller_id': row[3],
                'quantity': quantity,
                'unit_price_cents': unit_price,
                'line_total_cents': line_total,
                'fulfilled_at': row[6],
            }
        )

    total_cents = computed_total if computed_total else header[4]
    return {
        'order_id': header[0],
        'buyer': {
            'id': header[1],
            'full_name': header[5],
            'address': header[6],
            'email': header[7],
        },
        'created_at': header[2],
        'fulfilled': bool(header[3]),
        'total_cents': total_cents,
        'line_items': line_items,
    }


@bp.app_context_processor
def inject_helpers():
    return {'format_money': _format_money}


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
            for error in errors:
                flash(error, 'error')
            return render_template(
                'account/register.html',
                email=email,
                full_name=full_name,
                address=address,
            )

        try:
            user = User.create(email, full_name, address, password)
        except IntegrityError:
            flash('Email is already registered.', 'error')
            return render_template(
                'account/register.html',
                email=email,
                full_name=full_name,
                address=address,
            )

        with current_app.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO account_balance (user_id, balance_cents)
                    VALUES (:user_id, 0)
                    ON CONFLICT (user_id) DO NOTHING
                    """
                ),
                {'user_id': user.id},
            )

        session.clear()
        session['user_id'] = user.id
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

        user = User.authenticate(email, password)
        if not user:
            flash('Invalid email or password.', 'error')
            return render_template('account/login.html', email=email)

        session.clear()
        session['user_id'] = user.id
        flash('Logged in successfully.', 'success')
        next_url = request.args.get('next')
        return redirect(next_url or url_for('account.account_home'))

    return render_template('account/login.html')


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('account.login'))


@bp.route('/account')
@login_required
def account_home():
    balance_cents = User.get_balance(g.user.id)
    return render_template(
        'account/account.html',
        user=g.user,
        balance_cents=balance_cents,
    )


@bp.route('/account/edit', methods=['GET', 'POST'])
@login_required
def account_edit():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        address = request.form.get('address', '').strip()
        new_password = request.form.get('new_password', '')

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not address:
            errors.append('Address is required.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('account/account_edit.html', user=g.user)

        User.update_profile(g.user.id, full_name, address)
        g.user.full_name = full_name
        g.user.address = address

        if new_password:
            User.update_password(g.user.id, new_password)
            flash('Password updated.', 'success')

        flash('Profile updated.', 'success')
        return redirect(url_for('account.account_home'))

    return render_template('account/account_edit.html', user=g.user)


@bp.route('/account/balance', methods=['GET', 'POST'])
@login_required
def account_balance():
    if request.method == 'POST':
        action = request.form.get('action')
        amount_raw = request.form.get('amount_dollars', '').strip()

        try:
            amount_dollars = int(amount_raw)
        except (TypeError, ValueError):
            flash('Enter a whole dollar amount.', 'error')
            return redirect(url_for('account.account_balance'))

        if amount_dollars <= 0:
            flash('Amount must be positive.', 'error')
            return redirect(url_for('account.account_balance'))

        delta_cents = amount_dollars * 100
        note = ''

        if action == 'topup':
            note = 'Top up'
        elif action == 'withdraw':
            delta_cents = -delta_cents
            note = 'Withdraw'
        else:
            flash('Select an action.', 'error')
            return redirect(url_for('account.account_balance'))

        try:
            User.adjust_balance(g.user.id, delta_cents, note)
            flash('Balance updated.', 'success')
        except ValueError:
            flash('Withdrawal would make balance negative.', 'error')

        return redirect(url_for('account.account_balance'))

    balance_cents = User.get_balance(g.user.id)
    history = User.get_balance_history(g.user.id)
    return render_template(
        'account/balance.html',
        balance_cents=balance_cents,
        history=history,
    )


@bp.route('/account/purchases')
@login_required
def account_purchases():
    page = _parse_positive_int(request.args.get('page', 1), 1)
    per_page = _parse_positive_int(
        request.args.get('per_page', PURCHASES_PAGE_SIZE),
        PURCHASES_PAGE_SIZE,
        minimum=5,
        maximum=25,
    )
    offset = (page - 1) * per_page
    result = purchases.get_purchases_for_user(g.user.id, limit=per_page, offset=offset)
    total_orders = result['total_orders']
    total_pages = max(1, math.ceil(total_orders / per_page)) if total_orders else 1

    if total_orders == 0:
        page = 1

    if total_orders and offset >= total_orders:
        page = total_pages
        offset = (page - 1) * per_page
        result = purchases.get_purchases_for_user(g.user.id, limit=per_page, offset=offset)

    return render_template(
        'account/purchases.html',
        orders=result['orders'],
        page=page,
        per_page=per_page,
        total_orders=total_orders,
        total_pages=total_pages,
    )


@bp.route('/account/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = _get_order_detail(order_id)
    if order is None:
        abort(404)
    if order['buyer']['id'] != g.user.id:
        abort(403)
    return render_template('account/order_detail.html', order=order)


@bp.route('/api/users/<int:user_id>/purchases')
def api_user_purchases(user_id):
    """Public API that returns paginated orders for a user."""
    user = User.get(user_id)
    if user is None:
        return jsonify({'error': 'user not found'}), 404

    page = _parse_positive_int(request.args.get('page', 1), 1)
    per_page = _parse_positive_int(
        request.args.get('per_page', PURCHASES_PAGE_SIZE),
        PURCHASES_PAGE_SIZE,
        maximum=50,
    )
    offset = (page - 1) * per_page
    result = purchases.get_purchases_for_user(user_id, limit=per_page, offset=offset)
    total_orders = result['total_orders']
    total_pages = max(1, math.ceil(total_orders / per_page)) if total_orders else 1

    if total_orders == 0:
        page = 1

    if total_orders and offset >= total_orders:
        page = total_pages
        offset = (page - 1) * per_page
        result = purchases.get_purchases_for_user(user_id, limit=per_page, offset=offset)

    serialized_orders = [_serialize_order(order) for order in result['orders']]
    return jsonify(
        {
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
            },
            'page': page,
            'per_page': per_page,
            'total_orders': total_orders,
            'total_pages': total_pages,
            'orders': serialized_orders,
        }
    )


@bp.route('/api/users/<int:user_id>/seller-reviews')
def api_user_seller_reviews(user_id):
    user = User.get(user_id)
    if user is None:
        return jsonify({'error': 'user not found'}), 404

    limit = _parse_positive_int(request.args.get('limit', 5), 5, maximum=25)
    reviews = seller_review.get_recent_reviews_for_seller(user_id, limit=limit)
    summary = seller_review.get_summary_for_seller(user_id)

    serialized_reviews = [
        {
            'id': review['id'],
            'rating': review['rating'],
            'body': review['body'],
            'created_at': _serialize_datetime(review['created_at']),
            'updated_at': _serialize_datetime(review['updated_at']),
            'reviewer': {
                'id': review['reviewer_id'],
                'full_name': review['reviewer_name'],
            },
        }
        for review in reviews
    ]
    serialized_summary = {
        'review_count': summary['review_count'],
        'average_rating': summary['average_rating'],
        'first_review_at': _serialize_datetime(summary['first_review_at']),
        'last_review_at': _serialize_datetime(summary['last_review_at']),
    }
    return jsonify(
        {
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
            },
            'summary': serialized_summary,
            'reviews': serialized_reviews,
        }
    )


@bp.route('/seller-reviews')
def seller_reviews_page():
    default_user_id = g.user.id if g.user else ''
    return render_template('seller_reviews.html', default_user_id=default_user_id)


@bp.route('/users/<int:user_id>')
def public_profile(user_id):
    user = User.get(user_id)
    if user is None:
        abort(404)

    purchase_summary = purchases.get_purchase_summary(user_id)
    seller_summary = seller_review.get_summary_for_seller(user_id)
    seller_reviews = seller_review.get_recent_reviews_for_seller(user_id, limit=10)

    return render_template(
        'account/public_user.html',
        user=user,
        purchase_summary=purchase_summary,
        seller_summary=seller_summary,
        seller_reviews=seller_reviews,
    )
