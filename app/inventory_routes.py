from flask import current_app as app
from flask import Blueprint, jsonify, request, render_template, redirect, url_for
from app.models.inventory import get_inventory_for_user, add_product_to_inventory, update_product_quantity, remove_product_from_inventory, get_product_by_id, get_inventory_item, get_orders_for_seller, get_order_details, mark_line_item_as_fulfilled
from math import ceil

bp = Blueprint('inventory', __name__)

@bp.route('/api/users/<int:user_id>/inventory', methods=['GET'])
def api_get_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return jsonify({"user_id": user_id, "items": items})

@bp.route('/users/<int:user_id>/inventory')
def view_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return render_template('inventory.html', inventory=items, owner_id=user_id)

#MANIPULATE INVENTORY

@bp.route('/users/<int:user_id>/inventory/add', methods=['GET', 'POST'])
def add_product(user_id):
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        quantity = int(request.form['quantity'])
        available = request.form['available'] == 'true'

        rows = app.db.execute("""
            SELECT id FROM Products WHERE name = :name
        """, name=name)

        if rows and len(rows) > 0:
            product_id = rows[0][0]
        else:

            app.db.execute("""
                INSERT INTO Products (name, price, available)
                VALUES (:name, :price, :available)
            """, name=name, price=price, available=available)

            rows = app.db.execute("""
                SELECT id FROM Products WHERE name = :name
            """, name=name)
            if rows and len(rows) > 0:
                product_id = rows[0][0]  
            else:
                raise Exception("Product could not be created or fetched.")

        add_product_to_inventory(user_id, product_id, quantity)

        return redirect(url_for('inventory.view_inventory', user_id=user_id))

    return render_template('add_product.html', user_id=user_id)

@bp.route('/users/<int:user_id>/inventory/<int:product_id>/remove', methods=['POST'])
def remove_product(user_id, product_id):
    remove_product_from_inventory(user_id, product_id)
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

    # Get the paginated orders and total count
    orders, total_orders = get_orders_for_seller(user_id, item_query, seller_query, start_date, end_date, page, per_page)

    # Calculate total pages for pagination
    total_pages = ceil(total_orders / per_page) if total_orders > 0 else 1

    return render_template(
        'seller-orders.html', 
        user_id=user_id, 
        orders=orders, 
        total_orders=total_orders, 
        page=page, 
        per_page=per_page, 
        total_pages=total_pages,  # Pass the correct total_pages
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
        # Call the function to mark the line item as fulfilled
        mark_line_item_as_fulfilled(user_id, order_id, line_item_id)

        # Redirect to the order details page after fulfillment to reflect the updated status
        return redirect(url_for('inventory.view_order_details', user_id=user_id, order_id=order_id))

    except Exception as e:
        # Log the error or print it for debugging (optional)
        app.logger.error(f"Error fulfilling line item: {e}")
        # Instead of showing an error page, just redirect back to the orders page
        return redirect(url_for('inventory.view_orders', user_id=user_id))
