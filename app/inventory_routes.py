from flask import current_app as app
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from app.models.inventory import get_inventory_for_user, add_product_to_inventory, update_product_quantity, remove_product_from_inventory, get_product_by_id, get_inventory_item, get_orders_for_seller, get_order_details, mark_line_item_as_fulfilled, get_order_analytics, get_top_buyers
from math import ceil

bp = Blueprint('inventory', __name__)

@bp.route('/api/users/<int:user_id>/inventory', methods=['GET'])
def api_get_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return jsonify({"user_id": user_id, "items": items})

@bp.route('/users/<int:user_id>/inventory')
def view_inventory(user_id):
    page = request.args.get('page', 1, type=int)
    items, total_pages = get_inventory_for_user(user_id, page=page)
    
    return render_template('inventory.html', inventory=items, owner_id=user_id, page=page, total_pages=total_pages)

#MANIPULATE INVENTORY
@bp.route('/users/<int:user_id>/inventory/add', methods=['GET', 'POST'])
def add_product(user_id):
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        quantity = int(request.form['quantity'])
        available = request.form['available'] == 'true'

        # Check if product exists in Products
        rows = app.db.execute("""
            SELECT id FROM Products WHERE name = :name
        """, name=name)

        if rows:
            product_id = rows[0][0]
        else:
            app.db.execute("""
                INSERT INTO Products (name, price, available)
                VALUES (:name, :price, :available)
            """, name=name, price=price, available=available)

            rows = app.db.execute("""
                SELECT id FROM Products WHERE name = :name
            """, name=name)

            if not rows:
                raise Exception("Product could not be created or fetched.")

            product_id = rows[0][0]

        # Check inventory duplicate
        existing = app.db.execute("""
            SELECT 1 FROM Inventory 
            WHERE user_id = :uid AND product_id = :pid
        """, uid=user_id, pid=product_id)

        if existing:
            return render_template(
                "add_product.html",
                user_id=user_id,
                error="This product is already in your inventory."
            )

        # Otherwise add
        app.db.execute("""
            INSERT INTO Inventory (user_id, product_id, quantity)
            VALUES (:uid, :pid, :qty)
        """, uid=user_id, pid=product_id, qty=quantity)

        return redirect(url_for("inventory.view_inventory", user_id=user_id))

    return render_template("add_product.html", user_id=user_id)

@bp.route('/users/<int:user_id>/inventory/<int:product_id>/remove', methods=['POST'])
def remove_product(user_id, product_id):
    try:
        # Attempt to remove the product
        remove_product_from_inventory(user_id, product_id)
        flash("Product removed from inventory.", "success")
    except Exception as e:
        # If the function raises an error (e.g., outstanding order)
        flash(str(e), "danger")  # Display the message in a popup/alert

    return redirect(url_for('inventory.view_inventory', user_id=user_id))


@bp.route('/users/<int:user_id>/inventory/<int:product_id>/edit', methods=['GET', 'POST'])
def edit_product(user_id, product_id):
    product = get_product_by_id(product_id) 
    inventory_item = get_inventory_item(user_id, product_id) 

    if request.method == 'POST':
        new_quantity = int(request.form['quantity'])
        update_product_quantity(user_id, product_id, new_quantity)
        return redirect(url_for('inventory.view_inventory', user_id=user_id))
    
    return render_template('edit_product.html', 
                           user_id=user_id, 
                           product=product, 
                           inventory_item=inventory_item)

# INVENTORY ANALYTICS
@bp.route('/users/<int:user_id>/analytics/orders')
def view_order_analytics(user_id):
    top_products = get_order_analytics(user_id)
    return render_template(
        'order_analytics.html',
        user_id=user_id,
        top_products=top_products,
    )

# SELLER ANALYTICS
@bp.route('/users/<int:user_id>/analytics/sellers')
def view_seller_analytics(user_id):
    buyer_stats = get_top_buyers(user_id)
    return render_template('seller_analytics.html', user_id=user_id, buyer_stats=buyer_stats)

#ORDER HISTORY/FULFILLMENT
@bp.route('/users/<int:user_id>/orders', methods=['GET'])
def view_orders(user_id):
    item_query = request.args.get('item', '')
    seller_query = request.args.get('seller', '')
    start_date = request.args.get('start', '')
    end_date = request.args.get('end', '')
    page = int(request.args.get('page', 1)) 
    per_page = int(request.args.get('per_page', 10)) 

    start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    end_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None

    offset = (page - 1) * per_page

    orders, total_orders = get_orders_for_seller(user_id, per_page, offset, item_query, seller_query, start_date, end_date)

    total_pages = ceil(total_orders / per_page) if total_orders > 0 else 1
    total_pages = min(total_pages, 10) 

    return render_template(
        'seller-orders.html', 
        user_id=user_id, 
        orders=orders, 
        total_orders=total_orders, 
        page=page, 
        per_page=per_page, 
        total_pages=total_pages, 
        item_query=item_query,
        start_filter=start_date,
        end_filter=end_date
    )

@bp.route('/users/<int:user_id>/orders/<int:order_id>', methods=['GET'])
def view_order_details(user_id, order_id):
    order_details = get_order_details(user_id, order_id)

    if not order_details:
        return render_template('error.html', message="Order not found or you are not the seller for this order."), 404

    return render_template('seller_order_details.html', user_id=user_id, order_id=order_id, order_details=order_details)

@bp.route('/users/<int:user_id>/orders/<int:order_id>/line_item/<int:line_item_id>/fulfill', methods=['POST'])
def fulfill_line_item(user_id, order_id, line_item_id):
    try:
        mark_line_item_as_fulfilled(user_id, order_id, line_item_id)

        return redirect(url_for('inventory.view_order_details', user_id=user_id, order_id=order_id))

    except Exception as e:
        app.logger.error(f"Error fulfilling line item: {e}")
        return redirect(url_for('inventory.view_orders', user_id=user_id))
