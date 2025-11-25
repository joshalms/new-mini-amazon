from flask import current_app
from app.db import DB

def _db():
    app = current_app._get_current_object()
    if hasattr(app, "db") and isinstance(app.db, DB):
        return app.db
    return DB(app)

def get_or_create_cart(user_id):
    db = _db()
    # CHANGED: Cart → "Cart"
    rows = db.execute('SELECT id FROM "Cart" WHERE user_id = :uid', uid=user_id)
    if rows:
        return rows[0][0]
    # CHANGED: Cart → "Cart"
    inserted = db.execute('INSERT INTO "Cart" (user_id) VALUES (:uid) RETURNING id', uid=user_id)
    return inserted[0][0]

def get_cart_for_user(user_id):
    db = _db()
    rows = db.execute("""
        SELECT ci.product_id, ci.quantity, p.name, p.price
        -- CHANGED: cartitem → "CartItem"
        FROM "CartItem" ci
        -- CHANGED: cart → "Cart"
        JOIN "Cart" c ON ci.cart_id = c.id
        -- CHANGED: products → "Products"
        LEFT JOIN "Products" p ON ci.product_id = p.id
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

    # CHANGED: CartItem → "CartItem"
    rows = db.execute('SELECT id, quantity FROM "CartItem" WHERE cart_id = :cid AND product_id = :pid',
                      cid=cart_id, pid=product_id)

    if rows:
        item_id, existing = rows[0]
        new_q = existing + int(quantity)
        if new_q <= 0:
            # CHANGED: CartItem → "CartItem"
            db.execute('DELETE FROM "CartItem" WHERE id = :id', id=item_id)
        else:
            # CHANGED: CartItem → "CartItem"
            db.execute('UPDATE "CartItem" SET quantity = :q WHERE id = :id', q=new_q, id=item_id)
    else:
        if int(quantity) > 0:
            # CHANGED: CartItem → "CartItem"
            db.execute('INSERT INTO "CartItem" (cart_id, product_id, quantity) VALUES (:cid, :pid, :q)',
                       cid=cart_id, pid=product_id, q=quantity)


def set_item_quantity(user_id, product_id, quantity=0):
    db = _db()
    cart_id = get_or_create_cart(user_id)

    if int(quantity) <= 0:
        # CHANGED: CartItem → "CartItem"
        db.execute('DELETE FROM "CartItem" WHERE cart_id = :cid AND product_id = :pid',
                   cid=cart_id, pid=product_id)
        return

    # CHANGED: CartItem → "CartItem"
    rows = db.execute('SELECT id FROM "CartItem" WHERE cart_id = :cid AND product_id = :pid',
                      cid=cart_id, pid=product_id)

    if rows:
        # CHANGED: CartItem → "CartItem"
        db.execute('UPDATE "CartItem" SET quantity = :q WHERE cart_id = :cid AND product_id = :pid',
                   q=quantity, cid=cart_id, pid=product_id)
    else:
        # CHANGED: CartItem → "CartItem"
        db.execute('INSERT INTO "CartItem" (cart_id, product_id, quantity) VALUES (:cid, :pid, :q)',
                   cid=cart_id, pid=product_id, q=quantity)


def clear_cart(user_id):
    db = _db()
    # CHANGED: CartItem → "CartItem", Cart → "Cart"
    db.execute('DELETE FROM "CartItem" WHERE cart_id = (SELECT id FROM "Cart" WHERE user_id = :uid)',
               uid=user_id)


def submit_order(user_id):
    """
    Submit cart as order. Validates inventory and balance, creates order,
    updates balances and inventories, then clears cart.
    """
    from app.models.user import User
    from sqlalchemy import text

    db = _db()

    # CHANGED: CartItem, Cart, Products → quoted forms
    cart_items = db.execute("""
        SELECT ci.product_id, ci.quantity, p.price, p.name
        FROM "CartItem" ci
        JOIN "Cart" c ON ci.cart_id = c.id
        JOIN "Products" p ON ci.product_id = p.id
        WHERE c.user_id = :uid
        ORDER BY ci.id
    """, uid=user_id)

    if not cart_items:
        return None, "Cart is empty"

    items_to_order = []
    total_cents = 0

    for item in cart_items:
        product_id, quantity, price, name = item

        if price is None:
            return None, f"Product '{name}' has no price"

        # CHANGED: Inventory → "Inventory"
        seller_rows = db.execute("""
            SELECT user_id, quantity 
            FROM "Inventory"
            WHERE product_id = :pid AND quantity >= :qty AND user_id != :buyer_id
            ORDER BY quantity DESC
            LIMIT 1
        """, pid=product_id, qty=quantity, buyer_id=user_id)

        if not seller_rows:
            return None, f"Product '{name}' has no seller with sufficient inventory (need {quantity})"

        seller_id = seller_rows[0][0]

        unit_price_cents = int(float(price) * 100)
        total_cents += unit_price_cents * quantity

        items_to_order.append({
            'product_id': product_id,
            'seller_id': seller_id,
            'quantity': quantity,
            'unit_price_cents': unit_price_cents,
            'name': name
        })

    buyer_balance = User.get_balance(user_id)
    if buyer_balance < total_cents:
        return None, f"Insufficient balance."

    try:
        with db.engine.begin() as conn:

            # CHANGED: orders → "orders"
            order_result = conn.execute(
                text("""
                    INSERT INTO "orders" (buyer_id, total_cents, fulfilled)
                    VALUES (:buyer_id, :total_cents, FALSE)
                    RETURNING id
                """),
                {'buyer_id': user_id, 'total_cents': total_cents}
            )
            order_id = order_result.fetchone()[0]

            for item in items_to_order:

                # CHANGED: order_items → "order_items"
                conn.execute(
                    text("""
                        INSERT INTO "order_items" 
                        (order_id, product_id, seller_id, quantity, unit_price_cents)
                        VALUES (:order_id, :product_id, :seller_id, :quantity, :unit_price_cents)
                    """),
                    item | {"order_id": order_id}
                )

                # CHANGED: Inventory → "Inventory"
                conn.execute(
                    text("""
                        UPDATE "Inventory"
                        SET quantity = quantity - :qty
                        WHERE user_id = :seller_id AND product_id = :product_id
                    """),
                    {
                        "qty": item["quantity"],
                        "seller_id": item["seller_id"],
                        "product_id": item["product_id"]
                    }
                )

            # Clear cart
            # CHANGED: CartItem → "CartItem", Cart → "Cart"
            conn.execute(
                text('DELETE FROM "CartItem" WHERE cart_id = (SELECT id FROM "Cart" WHERE user_id = :uid)'),
                {"uid": user_id}
            )

        return order_id, None

    except Exception as e:
        return None, f"Error processing order: {str(e)}"