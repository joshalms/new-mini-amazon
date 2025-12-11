"""
Demo Script & Security Notes
============================

Demo (Milestone 3 / Final Video) Walkthrough:
1. Start logged out and attempt to visit /users/me to show restricted access message.
2. Register a brand-new user via POST /api/users/register (show email validation fail first).
3. Log in with that user using POST /api/users/login (demonstrate bad password failure).
4. Visit /users/me to view the profile dashboard with balance + navigation links.
5. Update the profile successfully (e.g., change password) then attempt an illegal update
   by switching to an email that already exists and show the 400 error response.
6. Top up the balance, then attempt to withdraw more than available to trigger the
   insufficient funds error, followed by a valid withdrawal.
7. Browse products / checkout flow (handled by teammates) so that new orders exist.
8. Showcase the paginated / filtered table at /users/<id>/purchases and drill into
   /orders/<order_id> to highlight fulfillment details.
9. Visit /users/<id>/public to present the public profile and the placeholder
   “Seller Reviews” integration section for the Social module.

Security guarantee: every SQL statement in this module uses SQLAlchemy’s parameter
binding (current_app.db.execute(text(...), params)) or executes within an engine
transaction with parameters. No user-provided strings are interpolated into raw SQL,
preventing SQL injection vulnerabilities. All HTML is rendered with Jinja2’s automatic
escaping so user input is never rendered raw.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

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
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import seller_review
from app.models import purchases

bp = Blueprint('users', __name__, template_folder='templates')


def _get_json() -> Dict[str, Any]:
    """Return a safely parsed JSON payload (Spec §1)."""
    return request.get_json(silent=True) or {}


def _require_auth() -> int:
    """Ensure the current session is authenticated, returning the user id or aborting (Spec §1)."""
    user_id = session.get('user_id')
    if not user_id:
        response = jsonify({'error': 'authentication required'})
        response.status_code = 401
        abort(response)
    return user_id


def _ensure_login_for_page() -> Optional[Any]:
    """Redirect anonymous visitors to the login page when viewing protected HTML pages."""
    if not g.get('user'):
        flash('Please log in to view that page.', 'error')
        return redirect(url_for('account.login', next=request.path))
    return None


def _fetch_user_with_password(user_id: int) -> Optional[Tuple[Any, ...]]:
    """Fetch a full user row including password hash for profile updates (Spec §1.5)."""
    row = current_app.db.execute(
        """
SELECT id, email, full_name, address, created_at, password_hash
FROM Users
WHERE id = :user_id
""",
        user_id=user_id,
    )
    return row[0] if row else None


def _get_user_by_email(email: str) -> Optional[Tuple[Any, ...]]:
    """Return a user row given email using a parameterized query."""
    row = current_app.db.execute(
        """
SELECT id, password_hash
FROM Users
WHERE email = :email
""",
        email=email,
    )
    return row[0] if row else None


def _get_user_basic(user_id: int) -> Optional[Tuple[Any, ...]]:
    """Fetch lightweight user info for templates / payload shaping."""
    row = current_app.db.execute(
        """
SELECT id, email, full_name, address, created_at
FROM Users
WHERE id = :user_id
""",
        user_id=user_id,
    )
    return row[0] if row else None


def _get_balance_cents(user_id: int) -> int:
    """Return the current balance (Spec §2)."""
    row = current_app.db.execute(
        """
SELECT balance_cents
FROM account_balance
WHERE user_id = :user_id
""",
        user_id=user_id,
    )
    return row[0][0] if row else 0


def _get_balance_history(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent balance history entries ordered newest first (Spec §2.3)."""
    rows = current_app.db.execute(
        """
SELECT created_at, amount_cents, note
FROM balance_tx
WHERE user_id = :user_id
ORDER BY created_at DESC
LIMIT :limit
""",
        user_id=user_id,
        limit=limit,
    )
    history: List[Dict[str, Any]] = []
    for row in rows:
        created_at = row[0]
        history.append(
            {
                'created_at': created_at,
                'created_iso': created_at.isoformat() if isinstance(created_at, datetime) else created_at,
                'amount_cents': row[1],
                'note': row[2],
            }
        )
    return history


def _serialize_user(row: Tuple[Any, ...], balance_cents: int) -> Dict[str, Any]:
    """Shape a dict for API responses describing a user (Spec §1.4)."""
    return {
        'id': row[0],
        'email': row[1],
        'full_name': row[2],
        'address': row[3],
        'created_at': row[4].isoformat() if isinstance(row[4], datetime) else row[4],
        'balance_cents': balance_cents,
    }


def _parse_date_param(raw_value: Optional[str]) -> Optional[datetime]:
    """Parse date/datetime strings from query params (Spec §4.1 filtering)."""
    if not raw_value:
        return None
    cleaned = raw_value.strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _build_purchase_filters():
    """Return normalized filter kwargs and the raw values for template echoing."""
    item_query = (request.args.get('item') or '').strip()
    seller_raw = (request.args.get('seller') or '').strip()
    start_at = _parse_date_param(request.args.get('start'))
    end_at = _parse_date_param(request.args.get('end'))
    end_before = end_at + timedelta(days=1) if end_at else None

    seller_id = None
    seller_name = None
    if seller_raw:
        try:
            seller_id = int(seller_raw)
        except ValueError:
            seller_name = seller_raw

    return (
        {
            'item_query': item_query or None,
            'seller_id': seller_id,
            'seller_name': seller_name,
            'start_at': start_at,
            'end_before': end_before,
        },
        {
            'item_query': item_query,
            'seller_query': seller_raw,
            'start_filter': request.args.get('start', ''),
            'end_filter': request.args.get('end', ''),
        },
    )


def _serialize_purchase(order: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a purchase dict suitable for API responses."""
    created_at = order.get('order_created_at')
    serialized_items: List[Dict[str, Any]] = []
    for item in order.get('line_items', []):
        serialized_items.append(
            {
                'product_id': item.get('product_id'),
                'product_name': item.get('product_name'),
                'quantity': item.get('quantity'),
                'unit_price_cents': item.get('unit_price_cents'),
                'line_total_cents': item.get('line_total_cents'),
                'fulfilled': bool(item.get('fulfilled')),
                'seller_id': item.get('seller_id'),
                'seller_name': item.get('seller_name'),
            }
        )

    return {
        'order_id': order.get('order_id'),
        'order_created_at': created_at.isoformat() if isinstance(created_at, datetime) else created_at,
        'total_cents': order.get('total_cents'),
        'item_count': order.get('item_count'),
        'all_fulfilled': order.get('all_fulfilled'),
        'items': serialized_items,
    }


def _is_user_seller(user_id: int) -> bool:
    """Check whether the user appears as a seller in any order_items row (Spec §1.6)."""
    row = current_app.db.execute(
        """
SELECT 1
FROM order_items
WHERE seller_id = :user_id
LIMIT 1
""",
        user_id=user_id,
    )
    return bool(row)


# ---------------------------------------------------------------------------
# Authentication & Profile APIs (Spec §1)
# ---------------------------------------------------------------------------


@bp.route('/api/users/register', methods=['POST'])
def api_register():
    """Create a new user account (Spec §1.1 Registration)."""
    payload = _get_json()
    email = (payload.get('email') or '').strip().lower()
    full_name = (payload.get('full_name') or '').strip()
    address = (payload.get('address') or '').strip()
    password = payload.get('password') or ''

    errors: List[str] = []
    if '@' not in email:
        errors.append('email must contain "@"')
    if len(password) < 8:
        errors.append('password must be at least 8 characters long')
    if not full_name:
        errors.append('full_name is required')
    if not address:
        errors.append('address is required')

    if errors:
        return jsonify({'errors': errors}), 400

    with current_app.db.engine.begin() as conn:
        existing = conn.execute(
            text("SELECT 1 FROM Users WHERE email = :email"),
            {'email': email},
        ).first()
        if existing:
            return jsonify({'errors': ['email already registered']}), 400

        created = conn.execute(
            text(
                """
INSERT INTO Users (email, full_name, address, password_hash)
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
        if not created:
            return jsonify({'errors': ['could not create user']}), 400

        user_id = created[0]
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

    return jsonify({'user_id': user_id}), 201


@bp.route('/api/users/login', methods=['POST'])
def api_login():
    """Authenticate and establish a session (Spec §1.2 Login)."""
    payload = _get_json()
    email = (payload.get('email') or '').strip().lower()
    password = payload.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'invalid credentials'}), 401

    user_row = _get_user_by_email(email)
    if not user_row:
        return jsonify({'error': 'invalid credentials'}), 401
    user_id, password_hash = user_row

    if not check_password_hash(password_hash, password):
        return jsonify({'error': 'invalid credentials'}), 401

    session['user_id'] = user_id
    return jsonify({'user_id': user_id}), 200


@bp.route('/api/users/logout', methods=['POST'])
def api_logout():
    """Clear the current session (Spec §1.3 Logout)."""
    session.clear()
    return ('', 204)


@bp.route('/api/users/me', methods=['GET'])
def api_current_user():
    """Return profile details for the logged-in user (Spec §1.4 Profile)."""
    user_id = _require_auth()
    row = _get_user_basic(user_id)
    if not row:
        abort(404)
    balance_cents = _get_balance_cents(user_id)
    return jsonify(_serialize_user(row, balance_cents))


@bp.route('/api/users/me/update', methods=['POST'])
def api_update_profile():
    """Update mutable fields for the authenticated user (Spec §1.5 Profile update)."""
    user_id = _require_auth()
    payload = _get_json()

    row = _fetch_user_with_password(user_id)
    if not row:
        abort(404)

    _, current_email, current_full_name, current_address, created_at, current_hash = row

    new_email = payload.get('email')
    new_full_name = payload.get('full_name')
    new_address = payload.get('address')
    new_password = payload.get('new_password')
    old_password = payload.get('old_password')

    updates: List[str] = []
    params: Dict[str, Any] = {'user_id': user_id}

    if new_email is not None:
        candidate = new_email.strip().lower()
        if '@' not in candidate:
            return jsonify({'error': 'email must contain "@"'}), 400
        if candidate != current_email:
            conflict = current_app.db.execute(
                """
SELECT 1
FROM Users
WHERE email = :email AND id <> :user_id
""",
                email=candidate,
                user_id=user_id,
            )
            if conflict:
                return jsonify({'error': 'email already in use'}), 400
            updates.append('email = :email')
            params['email'] = candidate

    if new_full_name is not None:
        candidate = new_full_name.strip()
        if not candidate:
            return jsonify({'error': 'full_name cannot be empty'}), 400
        if candidate != current_full_name:
            updates.append('full_name = :full_name')
            params['full_name'] = candidate

    if new_address is not None:
        candidate = new_address.strip()
        if not candidate:
            return jsonify({'error': 'address cannot be empty'}), 400
        if candidate != current_address:
            updates.append('address = :address')
            params['address'] = candidate

    if new_password is not None:
        if len(new_password) < 8:
            return jsonify({'error': 'new_password must be at least 8 characters'}), 400
        if not old_password or not check_password_hash(current_hash, old_password):
            return jsonify({'error': 'old_password incorrect'}), 401
        updates.append('password_hash = :password_hash')
        params['password_hash'] = generate_password_hash(new_password)

    if not updates:
        balance_cents = _get_balance_cents(user_id)
        return jsonify(
            _serialize_user(
                (user_id, current_email, current_full_name, current_address, created_at),
                balance_cents,
            )
        )

    query = f"""
UPDATE Users
SET {', '.join(updates)}
WHERE id = :user_id
RETURNING id, email, full_name, address, created_at
"""
    updated = current_app.db.execute(query, **params)
    if not updated:
        abort(500)

    balance_cents = _get_balance_cents(user_id)
    return jsonify(_serialize_user(updated[0], balance_cents))


# ---------------------------------------------------------------------------
# Balance APIs (Spec §2)
# ---------------------------------------------------------------------------


@bp.route('/api/users/me/balance', methods=['GET'])
def api_balance():
    """Return the authenticated user's current balance (Spec §2.1)."""
    user_id = _require_auth()
    balance_cents = _get_balance_cents(user_id)
    return jsonify({'balance_cents': balance_cents})


@bp.route('/api/users/me/topup', methods=['POST'])
def api_top_up():
    """Increase balance and record a transaction (Spec §2.2 Top up)."""
    user_id = _require_auth()
    payload = _get_json()
    amount = payload.get('amount_cents')
    if not isinstance(amount, int) or amount <= 0:
        return jsonify({'error': 'amount_cents must be a positive integer'}), 400

    with current_app.db.engine.begin() as conn:
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
        updated = conn.execute(
            text(
                """
UPDATE account_balance
SET balance_cents = balance_cents + :amount
WHERE user_id = :user_id
RETURNING balance_cents
"""
            ),
            {'amount': amount, 'user_id': user_id},
        ).first()
        conn.execute(
            text(
                """
INSERT INTO balance_tx (user_id, amount_cents, note)
VALUES (:user_id, :amount_cents, 'top up')
"""
            ),
            {'user_id': user_id, 'amount_cents': amount},
        )

    balance_cents = updated[0] if updated else _get_balance_cents(user_id)
    return jsonify({'balance_cents': balance_cents})


@bp.route('/api/users/me/withdraw', methods=['POST'])
def api_withdraw():
    """Decrease balance if funds exist and record a transaction (Spec §2.3 Withdraw)."""
    user_id = _require_auth()
    payload = _get_json()
    amount = payload.get('amount_cents')
    if not isinstance(amount, int) or amount <= 0:
        return jsonify({'error': 'amount_cents must be a positive integer'}), 400

    with current_app.db.engine.begin() as conn:
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
        if amount > current_balance:
            return jsonify({'error': 'insufficient balance'}), 400

        updated = conn.execute(
            text(
                """
UPDATE account_balance
SET balance_cents = balance_cents - :amount
WHERE user_id = :user_id
RETURNING balance_cents
"""
            ),
            {'amount': amount, 'user_id': user_id},
        ).first()
        conn.execute(
            text(
                """
INSERT INTO balance_tx (user_id, amount_cents, note)
VALUES (:user_id, :amount_cents, 'withdraw')
"""
            ),
            {'user_id': user_id, 'amount_cents': -amount},
        )

    balance_cents = updated[0] if updated else _get_balance_cents(user_id)
    return jsonify({'balance_cents': balance_cents})


@bp.route('/api/users/me/balance/history', methods=['GET'])
def api_balance_history():
    """Return recent balance transactions (Spec §2.3)."""
    user_id = _require_auth()

    limit_param = request.args.get('limit', default='20')
    try:
        limit = max(1, min(100, int(limit_param)))
    except ValueError:
        limit = 20

    history = _get_balance_history(user_id, limit)
    serialized = [
        {
            'created_at': entry['created_iso'],
            'amount_cents': entry['amount_cents'],
            'note': entry['note'],
        }
        for entry in history
    ]
    return jsonify({'history': serialized})


# ---------------------------------------------------------------------------
# Purchase & Order APIs (Spec §3)
# ---------------------------------------------------------------------------


@bp.route('/api/users/<int:user_id>/purchases', methods=['GET'])
def api_user_purchases(user_id: int):
    """Return paginated purchases for a buyer (Spec §3.1)."""
    requester_id = _require_auth()
    if requester_id != user_id:
        return jsonify({'error': 'not authorized for this purchase history'}), 403

    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get('per_page', '10'))
    except ValueError:
        per_page = 10
    per_page = max(1, min(50, per_page))
    offset = (page - 1) * per_page

    filter_kwargs, _ = _build_purchase_filters()
    result = purchases.get_purchases_for_user(
        user_id,
        limit=per_page,
        offset=offset,
        **filter_kwargs,
    )
    total = result['total_orders']
    serialized = [_serialize_purchase(order) for order in result['orders']]
    return jsonify(
        {
            'page': page,
            'per_page': per_page,
            'total': total,
            'items': serialized,
        }
    )


@bp.route('/api/orders/<int:order_id>', methods=['GET'])
def api_order_detail(order_id: int):
    """Return order header and line items (Spec §3.2)."""
    detail = purchases.get_order_detail(order_id)
    if not detail:
        return jsonify({'error': 'order not found'}), 404
    normalized_lines = []
    for item in detail.get('line_items', []):
        fulfilled_at = item.get('fulfilled_at')
        normalized_lines.append(
            {
                **item,
                'fulfilled_at': fulfilled_at.isoformat() if isinstance(fulfilled_at, datetime) else fulfilled_at,
            }
        )
    payload = {
        **detail,
        'created_at': detail['created_at'].isoformat()
        if isinstance(detail['created_at'], datetime)
        else detail['created_at'],
        'line_items': normalized_lines,
    }
    return jsonify(payload)


# ---------------------------------------------------------------------------
# HTML Views (Spec §1.4, §1.6, §4)
# ---------------------------------------------------------------------------


@bp.route('/users/me', methods=['GET'])
def users_me():
    """Render the authenticated user's account dashboard (Spec §1.4 & §4.3)."""
    redirect_response = _ensure_login_for_page()
    if redirect_response:
        return redirect_response

    user = g.user
    balance_cents = _get_balance_cents(user.id)
    balance_history = _get_balance_history(user.id, limit=5)

    return render_template(
        'users/account.html',
        user_info={
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'address': user.address,
            'created_at': user.created_at,
        },
        balance_cents=balance_cents,
        balance_history=balance_history,
    )


@bp.route('/users/me/balance/history', methods=['GET'])
def users_balance_history():
    """Render an HTML table of balance history with basic analytics (Spec §2.3 & §4.5)."""
    redirect_response = _ensure_login_for_page()
    if redirect_response:
        return redirect_response

    user = g.user
    history = _get_balance_history(user.id, limit=50)

    total_inflow = sum(entry['amount_cents'] for entry in history if entry['amount_cents'] > 0)
    total_outflow = -sum(entry['amount_cents'] for entry in history if entry['amount_cents'] < 0)
    net_change = total_inflow - total_outflow

    return render_template(
        'users/balance_history.html',
        history=history,
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        net_change=net_change,
        current_balance=_get_balance_cents(user.id),
    )


@bp.route('/users/<int:user_id>/purchases', methods=['GET'])
def users_purchases(user_id: int):
    """Render filtered, paginated purchase history for a user (Spec §3.1 & §4.1)."""
    redirect_response = _ensure_login_for_page()
    if redirect_response:
        return redirect_response

    viewer = g.user
    if viewer.id != user_id:
        flash('You can only view your own purchase history.', 'error')
        return redirect(url_for('account.account_purchases'))

    user_row = _get_user_basic(user_id)
    if not user_row:
        abort(404)
    subject_user = {
        'id': user_row[0],
        'email': user_row[1],
        'full_name': user_row[2],
        'address': user_row[3],
        'created_at': user_row[4],
    }

    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get('per_page', '10'))
    except ValueError:
        per_page = 10
    per_page = max(1, min(50, per_page))
    offset = (page - 1) * per_page

    filter_kwargs, raw_filters = _build_purchase_filters()

    result = purchases.get_purchases_for_user(
        user_id,
        limit=per_page,
        offset=offset,
        **filter_kwargs,
    )
    total_orders = result['total_orders']
    total_pages = max(1, (total_orders + per_page - 1) // per_page) if total_orders else 1

    if total_orders and offset >= total_orders:
        page = total_pages
        offset = (page - 1) * per_page
        result = purchases.get_purchases_for_user(
            user_id,
            limit=per_page,
            offset=offset,
            **filter_kwargs,
        )

    filters_applied = any(
        [
            filter_kwargs.get('item_query'),
            filter_kwargs.get('seller_id') is not None,
            filter_kwargs.get('seller_name'),
            filter_kwargs.get('start_at'),
            filter_kwargs.get('end_before'),
        ]
    )

    return render_template(
        'purchases/list.html',
        viewer=viewer,
        owner_name=subject_user['full_name'],
        orders=result['orders'],
        page=page,
        per_page=per_page,
        total_orders=total_orders,
        total_pages=total_pages,
        item_query=raw_filters['item_query'],
        seller_query=raw_filters['seller_query'],
        start_filter=raw_filters['start_filter'],
        end_filter=raw_filters['end_filter'],
        filters_applied=filters_applied,
        list_endpoint='users.users_purchases',
        list_kwargs={'user_id': subject_user['id']},
        detail_endpoint='users.order_detail',
        detail_kwargs={},
    )


@bp.route('/users/search', methods=['GET'])
def users_search():
    """Allow authenticated users to search for other users by name and jump to their public profile."""
    redirect_response = _ensure_login_for_page()
    if redirect_response:
        return redirect_response

    query = (request.args.get('q') or '').strip()
    results: List[Dict[str, Any]] = []
    max_results = 25

    if query:
        pattern = f"%{query}%"
        rows = current_app.db.execute(
            """
SELECT
    u.id,
    u.full_name,
    u.email,
    u.address,
    u.created_at,
    EXISTS (
        SELECT 1 FROM order_items oi WHERE oi.seller_id = u.id
    ) AS is_seller
FROM Users u
WHERE u.full_name ILIKE :pattern
ORDER BY u.full_name
LIMIT :limit
""",
            pattern=pattern,
            limit=max_results,
        )
        for row in rows:
            results.append(
                {
                    'id': row[0],
                    'full_name': row[1],
                    'email': row[2],
                    'address': row[3],
                    'created_at': row[4],
                    'is_seller': bool(row[5]),
                }
            )

    return render_template('users/search.html', query=query, results=results, max_results=max_results)


@bp.route('/orders/<int:order_id>', methods=['GET'])
def order_detail(order_id: int):
    """Render a detailed order view with fulfillment info (Spec §3.2 & §4.2)."""
    redirect_response = _ensure_login_for_page()
    if redirect_response:
        return redirect_response

    detail = purchases.get_order_detail(order_id)
    if not detail:
        abort(404)
    if detail['buyer']['id'] != g.user.id:
        flash('You can only view your own orders.', 'error')
        return redirect(url_for('account.account_purchases'))
    return render_template(
        'purchases/detail.html',
        order=detail,
        back_url=url_for('users.users_purchases', user_id=g.user.id),
        show_reviews=False,
    )


@bp.route('/users/<int:user_id>/public', methods=['GET'])
def public_profile(user_id: int):
    """Render the public profile page (Spec §1.6 & §4.4)."""
    user_row = _get_user_basic(user_id)
    if not user_row:
        abort(404)

    sort = request.args.get('sort', 'date')
    is_seller = _is_user_seller(user_id)
    seller_reviews_list = seller_review.get_recent_reviews_for_seller(user_id, limit=10, sort=sort)
    seller_summary = seller_review.get_summary_for_seller(user_id)

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
        'users/public_profile.html',
        user_info={
            'id': user_row[0],
            'email': user_row[1],
            'full_name': user_row[2],
            'address': user_row[3],
            'created_at': user_row[4],
        },
        is_seller=is_seller,
        seller_reviews=seller_reviews_list,
        seller_summary=seller_summary,
        current_sort=sort,
        user_review=user_review,
        review_url=review_url,
        can_review=can_review,
        user_votes=user_votes,
    )


@bp.route('/users/me/reviews', methods=['GET'])
def users_reviews_placeholder():
    """Placeholder page linking to Social guru reviews module (integration helper)."""
    redirect_response = _ensure_login_for_page()
    if redirect_response:
        return redirect_response
    return render_template('users/reviews_placeholder.html')
