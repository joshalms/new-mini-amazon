# app/models/cart.py
from flask import current_app
from app.db import DB

def _db():
    app = current_app._get_current_object()
    if hasattr(app, "db") and isinstance(app.db, DB):
        return app.db
    return DB(app)

def get_or_create_cart(user_id):
    db = _db()
    rows = db.execute("SELECT id FROM Cart WHERE user_id = :uid", uid=user_id)
    if rows:
        return rows[0][0]
    inserted = db.execute("INSERT INTO Cart (user_id) VALUES (:uid) RETURNING id", uid=user_id)
    return inserted[0][0]

def get_cart_for_user(user_id):
    db = _db()
    rows = db.execute("""
      SELECT ci.product_id, ci.quantity, p.name, p.price
      FROM CartItem ci
      JOIN Cart c ON ci.cart_id = c.id
      LEFT JOIN Products p ON ci.product_id = p.id
      WHERE c.user_id = :uid
      ORDER BY ci.id
    """, uid=user_id)
    items = []
    for r in rows:
        pid, qty, name, price = r
        items.append({
            "product_id": pid,
            "quantity": qty,
            "name": name,
            "price": float(price) if price is not None else None
        })
    return items

def add_item_to_cart(user_id, product_id, quantity=1):
    db = _db()
    cart_id = get_or_create_cart(user_id)
    rows = db.execute("SELECT id, quantity FROM CartItem WHERE cart_id = :cid AND product_id = :pid", cid=cart_id, pid=product_id)
    if rows:
        item_id, existing = rows[0]
        new_q = existing + int(quantity)
        if new_q <= 0:
            db.execute("DELETE FROM CartItem WHERE id = :id", id=item_id)
        else:
            db.execute("UPDATE CartItem SET quantity = :q WHERE id = :id", q=new_q, id=item_id)
    else:
        if int(quantity) > 0:
            db.execute("INSERT INTO CartItem (cart_id, product_id, quantity) VALUES (:cid, :pid, :q)",
                       cid=cart_id, pid=product_id, q=quantity)

def set_item_quantity(user_id, product_id, quantity):
    db = _db()
    cart_id = get_or_create_cart(user_id)
    if int(quantity) <= 0:
        db.execute("DELETE FROM CartItem WHERE cart_id = :cid AND product_id = :pid", cid=cart_id, pid=product_id)
        return
    rows = db.execute("SELECT id FROM CartItem WHERE cart_id = :cid AND product_id = :pid", cid=cart_id, pid=product_id)
    if rows:
        db.execute("UPDATE CartItem SET quantity = :q WHERE cart_id = :cid AND product_id = :pid", q=quantity, cid=cart_id, pid=product_id)
    else:
        db.execute("INSERT INTO CartItem (cart_id, product_id, quantity) VALUES (:cid, :pid, :q)", cid=cart_id, pid=product_id, q=quantity)

def clear_cart(user_id):
    db = _db()
    db.execute("DELETE FROM CartItem WHERE cart_id = (SELECT id FROM Cart WHERE user_id = :uid)", uid=user_id)
