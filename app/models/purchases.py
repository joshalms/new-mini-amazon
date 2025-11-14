from flask import current_app as app


def get_purchases_for_user(user_id, limit=20, offset=0):
    """Return paginated orders with nested line items for a buyer."""
    try:
        limit_val = int(limit)
    except (TypeError, ValueError):
        limit_val = 20
    limit_val = max(1, min(50, limit_val))

    try:
        offset_val = int(offset)
    except (TypeError, ValueError):
        offset_val = 0
    offset_val = max(0, offset_val)

    total_rows = app.db.execute(
        """
SELECT COUNT(*) FROM orders WHERE buyer_id = :user_id
""",
        user_id=user_id,
    )
    total_orders = total_rows[0][0] if total_rows else 0
    if total_orders == 0:
        return {'orders': [], 'total_orders': 0}

    order_rows = app.db.execute(
        """
WITH selected_orders AS (
    SELECT
        o.id,
        o.created_at,
        o.total_cents,
        COUNT(oi.id) AS item_count,
        BOOL_AND(oi.fulfilled_at IS NOT NULL) AS all_fulfilled
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    WHERE o.buyer_id = :user_id
    GROUP BY o.id, o.created_at, o.total_cents
    ORDER BY o.created_at DESC, o.id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    so.id AS order_id,
    so.created_at,
    so.total_cents,
    so.item_count,
    so.all_fulfilled,
    oi.product_id,
    p.name AS product_name,
    oi.quantity,
    oi.unit_price_cents,
    (oi.quantity * oi.unit_price_cents)::BIGINT AS line_total_cents,
    (oi.fulfilled_at IS NOT NULL) AS fulfilled
FROM selected_orders so
JOIN order_items oi ON oi.order_id = so.id
JOIN products p ON p.id = oi.product_id
ORDER BY so.created_at DESC, so.id DESC, oi.id
""",
        user_id=user_id,
        limit=limit_val,
        offset=offset_val,
    )

    orders = []
    current_order = None
    for row in order_rows:
        order_id = row[0]
        if not current_order or current_order['order_id'] != order_id:
            current_order = {
                'order_id': order_id,
                'order_created_at': row[1],
                'total_cents': row[2],
                'item_count': int(row[3]),
                'all_fulfilled': bool(row[4]),
                'line_items': [],
            }
            orders.append(current_order)

        current_order['line_items'].append(
            {
                'product_id': row[5],
                'product_name': row[6],
                'quantity': row[7],
                'unit_price_cents': row[8],
                'line_total_cents': row[9],
                'fulfilled': bool(row[10]),
            }
        )

    return {'orders': orders, 'total_orders': total_orders}


def get_purchase_summary(user_id):
    """Return aggregate purchase metrics for displaying public stats."""
    row = app.db.execute(
        """
SELECT
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_cents), 0) AS total_cents,
    MAX(o.created_at) AS last_order_at
FROM orders o
WHERE o.buyer_id = :user_id
""",
        user_id=user_id,
    )
    if not row:
        return {'order_count': 0, 'total_cents': 0, 'last_order_at': None}

    stats = row[0]
    return {
        'order_count': stats[0] or 0,
        'total_cents': stats[1] or 0,
        'last_order_at': stats[2],
    }
