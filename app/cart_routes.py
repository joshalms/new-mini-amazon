# app/cart_routes.py
from flask import Blueprint, jsonify, request, render_template, g
from app.models.cart import get_cart_for_user, add_item_to_cart, set_item_quantity, clear_cart

bp = Blueprint('cart', __name__)


def _require_cart_owner(user_id):
    """Ensure the session user matches the cart owner."""
    user = getattr(g, 'user', None)
    if user is None:
        return jsonify({'error': 'authentication required'}), 401
    if user.id != user_id:
        return jsonify({'error': 'not authorized for this cart'}), 403
    return None


@bp.route('/api/cart/<int:user_id>', methods=['GET'])
def api_get_cart(user_id):
    error = _require_cart_owner(user_id)
    if error:
        return error
    items = get_cart_for_user(user_id)
    return jsonify({"user_id": user_id, "items": items})


@bp.route('/api/cart/<int:user_id>/add', methods=['POST'])
def api_add_item(user_id):
    error = _require_cart_owner(user_id)
    if error:
        return error
    data = request.get_json() or {}
    product_id = data.get('product_id')
    try:
        quantity = int(data.get('quantity', 1))
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be an integer"}), 400
    if product_id is None:
        return jsonify({"error": "missing product_id"}), 400
    add_item_to_cart(user_id, int(product_id), quantity)
    return jsonify({"ok": True})


@bp.route('/api/cart/<int:user_id>/set', methods=['POST'])
def api_set_item(user_id):
    error = _require_cart_owner(user_id)
    if error:
        return error
    data = request.get_json() or {}
    product_id = data.get('product_id')
    try:
        quantity = int(data.get('quantity', 0))
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be an integer"}), 400
    if product_id is None:
        return jsonify({"error": "missing product_id"}), 400
    set_item_quantity(user_id, int(product_id), quantity)
    return jsonify({"ok": True})


@bp.route('/api/cart/<int:user_id>/clear', methods=['POST'])
def api_clear_cart(user_id):
    error = _require_cart_owner(user_id)
    if error:
        return error
    clear_cart(user_id)
    return jsonify({"ok": True})


@bp.route('/cart')
def view_cart():
    user = getattr(g, 'user', None)
    requested_id = request.args.get('user_id', type=int)
    if requested_id is None:
        if user is None:
            return render_template('cart.html', items=[], total=0, user_id=None), 401
        requested_id = user.id
    elif user is None:
        return render_template('cart.html', items=[], total=0, user_id=None), 401
    elif user.id != requested_id:
        return render_template('cart.html', items=[], total=0, user_id=None), 403

    items = get_cart_for_user(requested_id)
    total = sum((item['quantity'] or 0) * (item['price'] or 0) for item in items)
    return render_template('cart.html', items=items, total=total, user_id=requested_id)
