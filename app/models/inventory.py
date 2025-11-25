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
def get_orders_for_seller(
    seller_id,
    limit=10,
    offset=0,
    item_query=None,
    seller_query=None,
    start_date=None,
    end_date=None,
):
    """
    Retrieve paginated orders for a seller with optional filters (item name, seller name, date range).
    The function returns the orders with their line items and summary information.
    """
    try:
        limit_val = int(limit)
    except (TypeError, ValueError):
        limit_val = 10
    limit_val = max(1, min(50, limit_val))

    try:
        offset_val = int(offset)
    except (TypeError, ValueError):
        offset_val = 0
    offset_val = max(0, offset_val)

    # Build dynamic filters
    conditions = ["oi.seller_id = :seller_id"]
    params = {'seller_id': seller_id}

    item_pattern = f"%{item_query.strip()}%" if item_query else None
    seller_pattern = f"%{seller_query.strip()}%" if seller_query else None

    if start_date:
        conditions.append("o.created_at >= :start_date")
        params['start_date'] = start_date
    if end_date:
        conditions.append("o.created_at <= :end_date")
        params['end_date'] = end_date
    if item_pattern:
        conditions.append("p.name ILIKE :item_pattern")
        params['item_pattern'] = item_pattern
    if seller_pattern:
        conditions.append("u.full_name ILIKE :seller_pattern")
        params['seller_pattern'] = seller_pattern

    where_clause = " AND ".join(conditions)

    # Count the total number of matching orders
    total_rows = app.db.execute(
        f"""
        SELECT COUNT(DISTINCT o.id)
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        LEFT JOIN users u ON u.id = o.buyer_id
        WHERE {where_clause}
        """,
        **params,
    )
    total_orders = total_rows[0][0] if total_rows else 0
    if total_orders == 0:
        return [], total_orders

    # Main query to get order details, including aggregated item count and buyer info
    order_rows = app.db.execute(
        f"""
        WITH filtered_line_items AS (
            SELECT
                o.id AS order_id,
                o.created_at,
                o.total_cents,
                oi.id AS order_item_id,
                oi.product_id,
                p.name AS product_name,
                oi.quantity,
                oi.unit_price_cents,
                (oi.quantity * oi.unit_price_cents)::BIGINT AS line_total_cents,
                o.fulfilled,
                oi.seller_id,
                u.full_name AS buyer_name,
                u.address AS buyer_address
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN products p ON p.id = oi.product_id
            LEFT JOIN users u ON u.id = o.buyer_id
            WHERE {where_clause}
        ),
        order_summary AS (
            SELECT
                order_id,
                MAX(created_at) AS order_created_at,
                MAX(total_cents) AS total_cents,
                SUM(quantity) AS item_count,  -- SUM(quantity) to get total item count per order
                BOOL_AND(fulfilled) AS all_fulfilled
            FROM filtered_line_items
            GROUP BY order_id
        ),
        paged_orders AS (
            SELECT order_id, order_created_at
            FROM order_summary
            ORDER BY order_created_at DESC, order_id DESC
            LIMIT :limit OFFSET :offset
        )
        SELECT
            po.order_id,
            os.order_created_at,
            os.total_cents,
            os.item_count,
            os.all_fulfilled,
            fli.order_item_id,
            fli.product_id,
            fli.product_name,
            fli.quantity,
            fli.unit_price_cents,
            fli.line_total_cents,
            fli.fulfilled,
            fli.seller_id,
            fli.buyer_name,
            fli.buyer_address
        FROM paged_orders po
        JOIN order_summary os ON os.order_id = po.order_id
        JOIN filtered_line_items fli ON fli.order_id = po.order_id
        ORDER BY os.order_created_at DESC, po.order_id DESC, fli.order_item_id
        """,
        **params,
        limit=limit_val,
        offset=offset_val,
    )

    # Organize the fetched data into order structures
    orders = []
    current_order = None
    for row in order_rows:
        order_id = row[0]
        if not current_order or current_order['order_id'] != order_id:
            current_order = {
                'order_id': order_id,
                'order_created_at': row[1],
                'total_cents': row[2],
                'item_count': int(row[3]),  # item_count is now correctly summed
                'fulfilled': bool(row[4]),
                'buyer_name': row[13],
                'buyer_address': row[14],
                'line_items': [],
            }
            orders.append(current_order)

        # Add line item details (does not affect item count, which is aggregated)
        current_order['line_items'].append(
            {
                'order_item_id': row[5],
                'product_id': row[6],
                'product_name': row[7],
                'quantity': row[8],  # This is the quantity of the specific line item
                'unit_price_cents': row[9],
                'line_total_cents': row[10],
                'fulfilled': bool(row[11]),
                'seller_id': row[12],
            }
        )

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