# app/models/cart.py
from flask import current_app
from app.db import DB


class CartError(RuntimeError):
    """Raised when cart operations cannot be completed safely."""


def _db():
    app = current_app._get_current_object()
    if hasattr(app, "db") and isinstance(app.db, DB):
        return app.db
    return DB(app)


def _ensure_product_available(db, product_id):
    """
    Ensure the product exists and is marked available before inserting a new cart row.
    """
    rows = db.execute("SELECT available FROM Products WHERE id = :pid", pid=product_id)
    if not rows:
        raise CartError("Product does not exist.")
    available = rows[0][0]
    if available is not None and not bool(available):
        raise CartError("Product is not available for purchase right now.")

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
    qty = int(quantity)
    cart_id = get_or_create_cart(user_id)
    rows = db.execute(
        "SELECT id, quantity FROM CartItem WHERE cart_id = :cid AND product_id = :pid",
        cid=cart_id,
        pid=product_id,
    )
    if rows:
        item_id, existing = rows[0]
        new_q = existing + qty
        if new_q <= 0:
            db.execute("DELETE FROM CartItem WHERE id = :id", id=item_id)
        else:
            db.execute("UPDATE CartItem SET quantity = :q WHERE id = :id", q=new_q, id=item_id)
    else:
        if qty > 0:
            _ensure_product_available(db, product_id)
            db.execute(
                "INSERT INTO CartItem (cart_id, product_id, quantity) VALUES (:cid, :pid, :q)",
                cid=cart_id,
                pid=product_id,
                q=qty,
            )

def set_item_quantity(user_id, product_id, quantity=0):
    db = _db()
    qty = int(quantity)
    cart_id = get_or_create_cart(user_id)
    if qty <= 0:
        db.execute(
            "DELETE FROM CartItem WHERE cart_id = :cid AND product_id = :pid",
            cid=cart_id,
            pid=product_id,
        )
        return
    rows = db.execute(
        "SELECT id FROM CartItem WHERE cart_id = :cid AND product_id = :pid",
        cid=cart_id,
        pid=product_id,
    )
    if rows:
        db.execute(
            "UPDATE CartItem SET quantity = :q WHERE cart_id = :cid AND product_id = :pid",
            q=qty,
            cid=cart_id,
            pid=product_id,
        )
    else:
        _ensure_product_available(db, product_id)
        db.execute(
            "INSERT INTO CartItem (cart_id, product_id, quantity) VALUES (:cid, :pid, :q)",
            cid=cart_id,
            pid=product_id,
            q=qty,
        )

def clear_cart(user_id):
    db = _db()
    db.execute("DELETE FROM CartItem WHERE cart_id = (SELECT id FROM Cart WHERE user_id = :uid)", uid=user_id)

def submit_order(user_id):
    """
    Submit cart as order. Validates inventory and balance, creates order,
    updates balances and inventories, then clears cart.
    Returns (order_id, None) on success, or (None, error_message) on failure.
    """
    from app.models.user import User
    from sqlalchemy import text
    
    db = _db()
    
    # Get cart items with product info
    cart_items = db.execute("""
        SELECT ci.product_id, ci.quantity, p.price, p.name
        FROM CartItem ci
        JOIN Cart c ON ci.cart_id = c.id
        JOIN Products p ON ci.product_id = p.id
        WHERE c.user_id = :uid
        ORDER BY ci.id
    """, uid=user_id)
    
    if not cart_items:
        return None, "Cart is empty"
    
    # Validate all items before processing
    items_to_order = []
    total_cents = 0
    
    for item in cart_items:
        product_id, quantity, price, name = item
        
        if price is None:
            return None, f"Product '{name}' has no price"
        
        # Auto-select seller with sufficient inventory (exclude the buyer)
        seller_rows = db.execute("""
            SELECT user_id, quantity FROM Inventory
            WHERE product_id = :pid AND quantity >= :qty AND user_id != :buyer_id
            ORDER BY quantity DESC
            LIMIT 1
        """, pid=product_id, qty=quantity, buyer_id=user_id)
        
        if not seller_rows:
            return None, f"Product '{name}' has no seller with sufficient inventory (need {quantity})"
        
        seller_id = seller_rows[0][0]
        available_qty = seller_rows[0][1]
        
        unit_price_cents = int(float(price) * 100)
        line_total_cents = unit_price_cents * quantity
        total_cents += line_total_cents
        
        items_to_order.append({
            'product_id': product_id,
            'seller_id': seller_id,
            'quantity': quantity,
            'unit_price_cents': unit_price_cents,
            'name': name
        })
    
    # Check buyer balance
    buyer_balance = User.get_balance(user_id)
    if buyer_balance < total_cents:
        return None, f"Insufficient balance. Required: ${total_cents/100:.2f}, Available: ${buyer_balance/100:.2f}"
    
    # All validations passed - create order in transaction
    try:
        with db.engine.begin() as conn:
            # Create order
            order_result = conn.execute(
                text("""
                    INSERT INTO orders (buyer_id, total_cents, fulfilled)
                    VALUES (:buyer_id, :total_cents, FALSE)
                    RETURNING id
                """),
                {'buyer_id': user_id, 'total_cents': total_cents}
            )
            order_id = order_result.fetchone()[0]
            
            # Create order items and update inventories
            seller_totals = {}  # Track how much to pay each seller
            
            for item in items_to_order:
                # Create order item (seller_id can be NULL if not assigned)
                conn.execute(
                    text("""
                        INSERT INTO order_items (order_id, product_id, seller_id, quantity, unit_price_cents)
                        VALUES (:order_id, :product_id, :seller_id, :quantity, :unit_price_cents)
                    """),
                    {
                        'order_id': order_id,
                        'product_id': item['product_id'],
                        'seller_id': item['seller_id'],  # Can be None
                        'quantity': item['quantity'],
                        'unit_price_cents': item['unit_price_cents']
                    }
                )
                
                # Decrement inventory
                conn.execute(
                    text("""
                        UPDATE Inventory 
                        SET quantity = quantity - :qty
                        WHERE user_id = :seller_id AND product_id = :product_id
                    """),
                    {
                        'qty': item['quantity'],
                        'seller_id': item['seller_id'],
                        'product_id': item['product_id']
                    }
                )
                
                # Track seller earnings
                seller_earnings = item['unit_price_cents'] * item['quantity']
                if item['seller_id'] not in seller_totals:
                    seller_totals[item['seller_id']] = 0
                seller_totals[item['seller_id']] += seller_earnings
            
            # Update buyer balance (decrement)
            User.adjust_balance(user_id, -total_cents, f"Order #{order_id}")
            
            # Update seller balances (increment)
            for seller_id, earnings_cents in seller_totals.items():
                User.adjust_balance(seller_id, earnings_cents, f"Order #{order_id} sale")
            
            # Clear cart
            conn.execute(
                text("DELETE FROM CartItem WHERE cart_id = (SELECT id FROM Cart WHERE user_id = :uid)"),
                {'uid': user_id}
            )
        
        return order_id, None
        
    except Exception as e:
        return None, f"Error processing order: {str(e)}"
