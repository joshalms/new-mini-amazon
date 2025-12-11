from functools import wraps
import math
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

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
from app.models import product_review


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


def _parse_date(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, '%Y-%m-%d')
    except (TypeError, ValueError):
        return None


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
                'seller_id': item.get('seller_id'),
                'seller_name': item.get('seller_name'),
            }
            for item in order.get('line_items', [])
        ],
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
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        address = request.form.get('address', '').strip()
        new_password = request.form.get('new_password', '')

        errors = []
        if not email:
            errors.append('Email is required.')
        elif '@' not in email:
            errors.append('Enter a valid email address.')
        if not full_name:
            errors.append('Full name is required.')
        if not address:
            errors.append('Address is required.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('account/account_edit.html', user=g.user)

        if email != g.user.email and User.email_exists(email, exclude_user_id=g.user.id):
            flash('That email is already registered to another account.', 'error')
            return render_template('account/account_edit.html', user=g.user)

        try:
            updated = User.update_profile(g.user.id, full_name, address, email=email)
        except IntegrityError:
            flash('That email is already registered to another account.', 'error')
            return render_template('account/account_edit.html', user=g.user)

        if not updated:
            flash('Could not update your profile right now. Please try again.', 'error')
            return render_template('account/account_edit.html', user=g.user)

        g.user.email = email
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
            amount_decimal = Decimal(amount_raw)
        except (TypeError, InvalidOperation):
            flash('Enter a valid amount in dollars and cents.', 'error')
            return redirect(url_for('account.account_balance'))

        decimal_places = -amount_decimal.as_tuple().exponent if amount_decimal.as_tuple().exponent < 0 else 0
        if decimal_places > 2:
            flash('Amount cannot have more than two decimal places.', 'error')
            return redirect(url_for('account.account_balance'))

        amount_decimal = amount_decimal.quantize(Decimal('0.01'))
        if amount_decimal <= 0:
            flash('Amount must be positive.', 'error')
            return redirect(url_for('account.account_balance'))

        delta_cents = int(amount_decimal * 100)
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

    item_query = (request.args.get('item') or '').strip()
    seller_raw = (request.args.get('seller') or '').strip()
    start_at = _parse_date(request.args.get('start'))
    end_at = _parse_date(request.args.get('end'))
    end_before = end_at + timedelta(days=1) if end_at else None

    seller_id = None
    seller_name = None
    if seller_raw:
        try:
            seller_id = int(seller_raw)
        except ValueError:
            seller_name = seller_raw

    filter_kwargs = {
        'item_query': item_query or None,
        'seller_id': seller_id,
        'seller_name': seller_name,
        'start_at': start_at,
        'end_before': end_before,
    }

    result = purchases.get_purchases_for_user(
        g.user.id,
        limit=per_page,
        offset=offset,
        **filter_kwargs,
    )
    total_orders = result['total_orders']
    total_pages = max(1, math.ceil(total_orders / per_page)) if total_orders else 1

    if total_orders == 0:
        page = 1

    if total_orders and offset >= total_orders:
        page = total_pages
        offset = (page - 1) * per_page
        result = purchases.get_purchases_for_user(
            g.user.id,
            limit=per_page,
            offset=offset,
            **filter_kwargs,
        )

    return render_template(
        'purchases/list.html',
        owner_name=g.user.full_name,
        orders=result['orders'],
        page=page,
        per_page=per_page,
        total_orders=total_orders,
        total_pages=total_pages,
        item_query=item_query,
        seller_query=seller_raw,
        start_filter=request.args.get('start', ''),
        end_filter=request.args.get('end', ''),
        filters_applied=bool(item_query or seller_raw or start_at or end_at),
        list_endpoint='account.account_purchases',
        list_kwargs={},
        detail_endpoint='account.order_detail',
        detail_kwargs={},
    )


@bp.route('/account/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = purchases.get_order_detail(order_id)
    if order is None:
        abort(404)
    if order['buyer']['id'] != g.user.id:
        abort(403)
    # Add review status for each line item
    for item in order['line_items']:
        item['product_review'] = product_review.get_user_review_for_product(g.user.id, item['product_id'])
        item['seller_review'] = seller_review.get_user_review_for_seller(g.user.id, item['seller_id']) if item['seller_id'] else None
        item['product_review_url'] = url_for('account.review_product', order_id=order['order_id'], product_id=item['product_id'])
        if item['seller_id']:
            item['seller_review_url'] = url_for('account.review_seller', order_id=order['order_id'], seller_id=item['seller_id'])
    return render_template(
        'purchases/detail.html',
        order=order,
        back_url=url_for('account.account_purchases'),
        show_reviews=True,
    )


@bp.route('/api/users/<int:user_id>/purchases')
def api_user_purchases(user_id):
    """Public API that returns paginated orders for a user."""
    requester = getattr(g, 'user', None)
    if requester is None:
        return jsonify({'error': 'authentication required'}), 401
    if requester.id != user_id:
        return jsonify({'error': 'not authorized for this purchase history'}), 403

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

    item_query = (request.args.get('item') or '').strip()
    seller_raw = (request.args.get('seller') or '').strip()
    start_at = _parse_date(request.args.get('start'))
    end_at = _parse_date(request.args.get('end'))
    end_before = end_at + timedelta(days=1) if end_at else None

    seller_id = None
    seller_name = None
    if seller_raw:
        try:
            seller_id = int(seller_raw)
        except ValueError:
            seller_name = seller_raw

    filter_kwargs = {
        'item_query': item_query or None,
        'seller_id': seller_id,
        'seller_name': seller_name,
        'start_at': start_at,
        'end_before': end_before,
    }

    result = purchases.get_purchases_for_user(
        user_id,
        limit=per_page,
        offset=offset,
        **filter_kwargs,
    )
    total_orders = result['total_orders']
    total_pages = max(1, math.ceil(total_orders / per_page)) if total_orders else 1

    if total_orders == 0:
        page = 1

    if total_orders and offset >= total_orders:
        page = total_pages
        offset = (page - 1) * per_page
        result = purchases.get_purchases_for_user(
            user_id,
            limit=per_page,
            offset=offset,
            **filter_kwargs,
        )

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

    sort = request.args.get('sort', 'date')
    purchase_summary = purchases.get_purchase_summary(user_id)
    seller_summary = seller_review.get_summary_for_seller(user_id)
    seller_reviews_list = seller_review.get_recent_reviews_for_seller(user_id, limit=10, sort=sort)

    # check if logged-in user can review this seller
    user_review = None
    review_url = None
    can_review = False
    user_votes = {}

    if g.user and g.user.id != user_id:
        user_review = seller_review.get_user_review_for_seller(g.user.id, user_id)
        order_info = purchases.get_user_order_with_seller(g.user.id, user_id)
        if order_info:
            can_review = True
            review_url = url_for(
                'account.review_seller',
                order_id=order_info['order_id'],
                seller_id=user_id,
            )
    if g.user:
        user_votes = seller_review.get_user_votes_for_seller(g.user.id, user_id)

    return render_template(
        'account/public_user.html',
        user=user,
        purchase_summary=purchase_summary,
        seller_summary=seller_summary,
        seller_reviews=seller_reviews_list,
        current_sort=sort,
        user_review=user_review,
        review_url=review_url,
        can_review=can_review,
        user_votes=user_votes,
    )


@bp.route('/account/orders/<int:order_id>/review-product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def review_product(order_id, product_id):
    order = purchases.get_order_detail(order_id)
    if order is None:
        abort(404)
    if order['buyer']['id'] != g.user.id:
        abort(403)

    # Verify product is in the order
    item = next((i for i in order['line_items'] if i['product_id'] == product_id), None)
    if item is None:
        abort(404)

    existing = product_review.get_user_review_for_product(g.user.id, product_id)

    if request.method == 'POST':
        rating = _parse_positive_int(request.form.get('rating'), 5, minimum=1, maximum=5)
        body = request.form.get('body', '').strip()
        if existing:
            product_review.update_review(existing['id'], rating, body)
            flash('Review updated.', 'success')
        else:
            product_review.create_review(g.user.id, product_id, rating, body)
            flash('Review submitted.', 'success')
        return redirect(url_for('account.order_detail', order_id=order_id))

    return render_template(
        'account/review_form.html',
        order=order,
        item=item,
        review=existing,
        review_type='product',
    )


@bp.route('/account/orders/<int:order_id>/review-seller/<int:seller_id>', methods=['GET', 'POST'])
@login_required
def review_seller(order_id, seller_id):
    order = purchases.get_order_detail(order_id)
    if order is None:
        abort(404)
    if order['buyer']['id'] != g.user.id:
        abort(403)

    # Verify seller is in the order
    item = next((i for i in order['line_items'] if i['seller_id'] == seller_id), None)
    if item is None:
        abort(404)

    existing = seller_review.get_user_review_for_seller(g.user.id, seller_id)

    if request.method == 'POST':
        rating = _parse_positive_int(request.form.get('rating'), 5, minimum=1, maximum=5)
        body = request.form.get('body', '').strip()
        if existing:
            seller_review.update_review(existing['id'], rating, body)
            flash('Review updated.', 'success')
        else:
            seller_review.create_review(g.user.id, seller_id, rating, body)
            flash('Review submitted.', 'success')
        return redirect(url_for('account.order_detail', order_id=order_id))

    return render_template(
        'account/review_form.html',
        order=order,
        item=item,
        review=existing,
        review_type='seller',
    )


@bp.route('/account/reviews/product/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_product_review(review_id):
    existing = product_review.get_review_by_id(review_id)
    if existing is None:
        abort(404)
    if existing['user_id'] != g.user.id:
        abort(403)

    product_review.delete_review(review_id)
    flash('Review deleted.', 'success')

    next_url = request.form.get('next') or url_for('account.my_reviews')
    return redirect(next_url)


@bp.route('/account/reviews/seller/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_seller_review(review_id):
    existing = seller_review.get_review_by_id(review_id)
    if existing is None:
        abort(404)
    if existing['user_id'] != g.user.id:
        abort(403)

    seller_review.delete_review(review_id)
    flash('Review deleted.', 'success')

    next_url = request.form.get('next') or url_for('account.my_reviews')
    return redirect(next_url)


@bp.route('/account/reviews')
@login_required
def my_reviews():
    sort = request.args.get('sort', 'date')
    product_reviews = product_review.get_reviews_by_user(g.user.id, sort=sort)
    seller_reviews = seller_review.get_reviews_by_user(g.user.id, sort=sort)

    return render_template(
        'account/my_reviews.html',
        product_reviews=product_reviews,
        seller_reviews=seller_reviews,
        current_sort=sort,
    )


@bp.route('/api/reviews/product/<int:review_id>/vote', methods=['POST'])
@login_required
def vote_product_review(review_id):
    review = product_review.get_review_by_id(review_id)
    if review is None:
        return jsonify({'error': 'review not found'}), 404

    data = request.get_json() or {}
    vote_value = data.get('vote', 0)
    if vote_value not in (-1, 0, 1):
        return jsonify({'error': 'invalid vote value'}), 400

    current_vote = product_review.get_user_vote(g.user.id, review_id)
    # if clicking same vote, remove it; otherwise set new vote
    if current_vote == vote_value:
        product_review.set_vote(g.user.id, review_id, 0)
    else:
        product_review.set_vote(g.user.id, review_id, vote_value)

    counts = product_review.get_vote_counts(review_id)
    new_vote = product_review.get_user_vote(g.user.id, review_id)

    return jsonify({
        'upvotes': counts['upvotes'],
        'downvotes': counts['downvotes'],
        'user_vote': new_vote,
    })


@bp.route('/api/reviews/seller/<int:review_id>/vote', methods=['POST'])
@login_required
def vote_seller_review(review_id):
    review = seller_review.get_review_by_id(review_id)
    if review is None:
        return jsonify({'error': 'review not found'}), 404

    data = request.get_json() or {}
    vote_value = data.get('vote', 0)
    if vote_value not in (-1, 0, 1):
        return jsonify({'error': 'invalid vote value'}), 400

    current_vote = seller_review.get_user_vote(g.user.id, review_id)
    # if clicking same vote, remove it; otherwise set new vote
    if current_vote == vote_value:
        seller_review.set_vote(g.user.id, review_id, 0)
    else:
        seller_review.set_vote(g.user.id, review_id, vote_value)

    counts = seller_review.get_vote_counts(review_id)
    new_vote = seller_review.get_user_vote(g.user.id, review_id)

    return jsonify({
        'upvotes': counts['upvotes'],
        'downvotes': counts['downvotes'],
        'user_vote': new_vote,
    })
