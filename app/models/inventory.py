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