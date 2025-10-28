# app/cart_routes.py
from flask import Blueprint, jsonify, request, render_template, g
from app.models.cart import get_cart_for_user, add_item_to_cart, set_item_quantity, clear_cart

bp = Blueprint('cart', __name__)

@bp.route('/api/cart/<int:user_id>', methods=['GET'])
def api_get_cart(user_id):
    items = get_cart_for_user(user_id)
    return jsonify({"user_id": user_id, "items": items})

@bp.route('/api/cart/<int:user_id>/add', methods=['POST'])
def api_add_item(user_id):
    data = request.get_json() or {}
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    if product_id is None:
        return jsonify({"error": "missing product_id"}), 400
    add_item_to_cart(user_id, int(product_id), quantity)
    return jsonify({"ok": True})

@bp.route('/api/cart/<int:user_id>/set', methods=['POST'])
def api_set_item(user_id):
    data = request.get_json() or {}
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 0))
    if product_id is None:
        return jsonify({"error": "missing product_id"}), 400
    set_item_quantity(user_id, int(product_id), quantity)
    return jsonify({"ok": True})

@bp.route('/api/cart/<int:user_id>/clear', methods=['POST'])
def api_clear_cart(user_id):
    clear_cart(user_id)
    return jsonify({"ok": True})

@bp.route('/cart')
def view_cart():
    user_id = request.args.get('user_id', type=int)
    if user_id is None:
        user = getattr(g, 'user', None)
        if user is not None:
            user_id = user.id
    if user_id is None:
        return render_template('cart.html', items=[], total=0, user_id=None), 401
    items = get_cart_for_user(user_id)
    total = sum((item['quantity'] or 0) * (item['price'] or 0) for item in items)
    return render_template('cart.html', items=items, total=total, user_id=user_id)
