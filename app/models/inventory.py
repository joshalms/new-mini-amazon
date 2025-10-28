from flask import current_app as app

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