from flask import current_app as app


def get_purchases_for_user(
    user_id,
    limit=20,
    offset=0,
    item_query=None,
    seller_id=None,
    seller_name=None,
    start_at=None,
    end_before=None,
):
    """Return paginated orders with nested line items for a buyer, with optional filters."""
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

    # Build dynamic filters
    conditions = ["o.buyer_id = :user_id"]
    params = {'user_id': user_id}

    item_pattern = f"%{item_query.strip()}%" if item_query else None
    seller_pattern = f"%{seller_name.strip()}%" if seller_name else None

    if start_at is not None:
        conditions.append("o.created_at >= :start_at")
        params['start_at'] = start_at
    if end_before is not None:
        conditions.append("o.created_at < :end_before")
        params['end_before'] = end_before
    if item_pattern:
        conditions.append("p.name ILIKE :item_pattern")
        params['item_pattern'] = item_pattern
    if seller_id is not None:
        conditions.append("oi.seller_id = :seller_id")
        params['seller_id'] = seller_id
    if seller_pattern:
        conditions.append("s.full_name ILIKE :seller_pattern")
        params['seller_pattern'] = seller_pattern

    where_clause = " AND ".join(conditions)

    total_rows = app.db.execute(
        f"""
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
LEFT JOIN Users s ON s.id = oi.seller_id
WHERE {where_clause}
""",
        **params,
    )
    total_orders = total_rows[0][0] if total_rows else 0
    if total_orders == 0:
        return {'orders': [], 'total_orders': 0}

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
        (oi.fulfilled_at IS NOT NULL) AS fulfilled,
        oi.seller_id,
        s.full_name AS seller_name
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.id
    JOIN products p ON p.id = oi.product_id
    LEFT JOIN Users s ON s.id = oi.seller_id
    WHERE {where_clause}
),
order_summary AS (
    SELECT
        order_id,
        MAX(created_at) AS order_created_at,
        MAX(total_cents) AS total_cents,
        COUNT(order_item_id) AS item_count,
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
    fli.product_id,
    fli.product_name,
    fli.quantity,
    fli.unit_price_cents,
    fli.line_total_cents,
    fli.fulfilled,
    fli.seller_id,
    fli.seller_name
FROM paged_orders po
JOIN order_summary os ON os.order_id = po.order_id
JOIN filtered_line_items fli ON fli.order_id = po.order_id
ORDER BY os.order_created_at DESC, po.order_id DESC, fli.order_item_id
""",
        **params,
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
                'seller_id': row[11],
                'seller_name': row[12],
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
