from flask import current_app as app
from sqlalchemy import text

def get_inventory_for_user(user_id):
    rows = app.db.execute("""
        SELECT 
            i.product_id,
            i.quantity,
            p.name,
            p.price,
            p.available
        FROM Inventory i
        JOIN Products p ON i.product_id = p.id
        WHERE i.user_id = :uid
        ORDER BY p.name
    """, uid=user_id)
    
    items = []
    for r in rows:
        pid, qty, name, price, available = r
        items.append({
            "product_id": pid,
            "quantity": qty,
            "name": name,
            "price": float(price) if price is not None else None,
            "available": bool(available)
        })
    return items

def get_product_by_id(product_id):
    with app.db.engine.begin() as conn:
        result = conn.execute(text("""
            SELECT id, name, price, available
            FROM Products
            WHERE id = :pid
        """), {"pid": product_id})

        product = result.fetchone()

        if product:
            return product
        return None

def get_inventory_item(user_id, product_id):
    with app.db.engine.begin() as conn:
        result = conn.execute(text("""
            SELECT quantity 
            FROM Inventory 
            WHERE user_id = :uid AND product_id = :pid
        """), {"uid": user_id, "pid": product_id})

        inventory_item = result.fetchone()

        if inventory_item:
            return inventory_item
        return None

#MANIPULATE INVENTORY FUNCTIONALITY

def add_product_to_inventory(user_id, product_id, quantity):
    with app.db.engine.begin() as conn:
        result = conn.execute(text("""
            SELECT quantity FROM Inventory WHERE user_id = :uid AND product_id = :pid
        """), {"uid": user_id, "pid": product_id})

        existing_quantity = result.fetchone()

        if existing_quantity: 
            new_quantity = existing_quantity[0] + quantity
            conn.execute(text("""
                UPDATE Inventory 
                SET quantity = :qty 
                WHERE user_id = :uid AND product_id = :pid
            """), {"qty": new_quantity, "uid": user_id, "pid": product_id})
        else:
            conn.execute(text("""
                INSERT INTO Inventory (user_id, product_id, quantity) 
                VALUES (:uid, :pid, :qty)
            """), {"uid": user_id, "pid": product_id, "qty": quantity})

def update_product_quantity(user_id, product_id, new_quantity):
    with app.db.engine.begin() as conn:
        result = conn.execute(text("""
            SELECT quantity 
            FROM Inventory 
            WHERE user_id = :user_id AND product_id = :product_id
        """), {"user_id": user_id, "product_id": product_id})

        existing = result.fetchone()

        if not existing:
            return {"message": "Product not found in inventory"}, 404

        conn.execute(text("""
            UPDATE Inventory 
            SET quantity = :quantity 
            WHERE user_id = :user_id AND product_id = :product_id
        """), {"quantity": new_quantity, "user_id": user_id, "product_id": product_id})

    return {"message": "Product quantity updated successfully"}

def remove_product_from_inventory(user_id, product_id):
    with app.db.engine.begin() as conn:
        result = conn.execute(text("""
            SELECT 1 
            FROM Inventory 
            WHERE user_id = :user_id AND product_id = :product_id
        """), {"user_id": user_id, "product_id": product_id})

        existing = result.fetchone()

        if not existing:
            return {"message": "Product not found in inventory"}, 404

        conn.execute(text("""
            DELETE FROM Inventory 
            WHERE user_id = :user_id AND product_id = :product_id
        """), {"user_id": user_id, "product_id": product_id})

    return {"message": "Product removed from inventory"}

#ORDER VIEWING/FULFILLMENT FUNCTIONALITY
def get_orders_for_seller(seller_id, item_query=None, seller_query=None, start_date=None, end_date=None, page=1, per_page=10):
    params = {'seller_id': seller_id}
    filters = []  # We'll use filters for SQL conditions only, not pagination

    query = """
        SELECT o.id AS order_id, o.created_at AS order_created_at, o.total_cents, 
               SUM(oi.quantity) AS item_count, o.fulfilled, 
               u.full_name AS buyer_name, u.address AS buyer_address
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN users u ON o.buyer_id = u.id
        WHERE oi.seller_id = :seller_id
    """

    if item_query:
        query += " AND p.name ILIKE :item_query"
        filters.append(('item_query', f"%{item_query}%"))
    if seller_query:
        query += " AND u.full_name ILIKE :seller_query"
        filters.append(('seller_query', f"%{seller_query}%"))
    if start_date:
        query += " AND o.created_at >= :start_date"
        filters.append(('start_date', start_date))
    if end_date:
        query += " AND o.created_at <= :end_date"
        filters.append(('end_date', end_date))

    query += " GROUP BY o.id, u.id ORDER BY o.created_at DESC"

    # Add pagination parameters directly to params
    params['per_page'] = per_page
    params['offset'] = (page - 1) * per_page

    # Execute the query with pagination
    with app.db.engine.begin() as conn:
        result = conn.execute(text(query), {**params, **dict(filters)})
        orders = result.fetchall()

    # Separate query to count the total number of matching orders (without pagination)
    count_query = """
        SELECT COUNT(DISTINCT o.id)
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN users u ON o.buyer_id = u.id
        WHERE oi.seller_id = :seller_id
    """

    # Apply the same filters used for pagination
    if item_query:
        count_query += " AND p.name ILIKE :item_query"
    if seller_query:
        count_query += " AND u.full_name ILIKE :seller_query"
    if start_date:
        count_query += " AND o.created_at >= :start_date"
    if end_date:
        count_query += " AND o.created_at <= :end_date"

    # Get the count result for total orders
    with app.db.engine.begin() as conn:
        count_result = conn.execute(text(count_query), {**params, **dict(filters)})
        total_orders = count_result.scalar()  # Get the total count

    return orders, total_orders

def get_order_details(seller_id, order_id):
    query = """
        SELECT oi.id AS line_item_id, p.name AS product_name, oi.quantity, oi.unit_price_cents, oi.fulfilled_at
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.seller_id = :seller_id AND oi.order_id = :order_id
    """
    with app.db.engine.begin() as conn:
        result = conn.execute(text(query), {'seller_id': seller_id, 'order_id': order_id})
        return result.fetchall()

def mark_line_item_as_fulfilled(seller_id, order_id, line_item_id):
    query = """
        UPDATE order_items
        SET fulfilled_at = NOW()
        WHERE seller_id = :seller_id AND order_id = :order_id AND id = :line_item_id
    """
    with app.db.engine.begin() as conn:
        conn.execute(text(query), {'seller_id': seller_id, 'order_id': order_id, 'line_item_id': line_item_id})