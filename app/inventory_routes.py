from flask import current_app as app
from flask import Blueprint, jsonify, request, render_template, redirect, url_for
from app.models.inventory import get_inventory_for_user, add_product_to_inventory, update_product_quantity, remove_product_from_inventory, get_product_by_id, get_inventory_item

bp = Blueprint('inventory', __name__)

@bp.route('/api/users/<int:user_id>/inventory', methods=['GET'])
def api_get_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return jsonify({"user_id": user_id, "items": items})


@bp.route('/users/<int:user_id>/inventory')
def view_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return render_template('inventory.html', inventory=items, user_id=user_id)

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
