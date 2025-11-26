# app/cart_routes.py
from flask import Blueprint, jsonify, request, render_template, g, redirect, url_for, flash
from app.models.cart import (
    CartError,
    add_item_to_cart,
    clear_cart,
    get_cart_for_user,
    set_item_quantity,
    submit_order,
)

bp = Blueprint('cart', __name__)

@bp.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    """Add a product to the current user's cart via form submission."""
    user = getattr(g, 'user', None)
    if user is None:
        flash("You must be logged in to add items to the cart.", "error")
        return redirect(url_for('account.login', next=request.referrer))

    add_item_to_cart(user.id, product_id, quantity=1)
    flash("Product added to your cart!", "success")
    return redirect(request.referrer or url_for('index'))



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
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({"error": "product_id must be an integer"}), 400
    try:
        add_item_to_cart(user_id, product_id, quantity)
    except CartError as err:
        return jsonify({"error": str(err)}), 400
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
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({"error": "product_id must be an integer"}), 400
    try:
        set_item_quantity(user_id, product_id, quantity)
    except CartError as err:
        return jsonify({"error": str(err)}), 400
    return jsonify({"ok": True})


@bp.route('/api/cart/<int:user_id>/clear', methods=['POST'])
def api_clear_cart(user_id):
    error = _require_cart_owner(user_id)
    if error:
        return error
    clear_cart(user_id)
    return jsonify({"ok": True})


@bp.route('/api/cart/<int:user_id>/checkout', methods=['POST'])
def api_checkout(user_id):
    error = _require_cart_owner(user_id)
    if error:
        return error
    order_id, error_msg = submit_order(user_id)
    if error_msg:
        return jsonify({"error": error_msg}), 400
    return jsonify({"ok": True, "order_id": order_id})


@bp.route('/cart/checkout', methods=['POST'])
def checkout():
    user = getattr(g, 'user', None)
    if user is None:
        flash('Please log in to checkout', 'error')
        return redirect(url_for('account.login'))
    
    order_id, error_msg = submit_order(user.id)
    if error_msg:
        flash(error_msg, 'error')
        return redirect(url_for('cart.view_cart'))
    
    flash(f'Order #{order_id} placed successfully!', 'success')
    # Redirect to order detail page if available, otherwise purchases
    try:
        return redirect(url_for('users.order_detail', order_id=order_id))
    except:
        return redirect(url_for('account.account_purchases'))


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
