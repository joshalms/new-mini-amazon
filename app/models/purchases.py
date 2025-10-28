from flask import current_app as app


def get_purchases_for_user(user_id):
    rows = app.db.execute(
        """
SELECT
    o.id AS order_id,
    o.created_at AS order_created_at,
    p.id AS product_id,
    p.name AS product_name,
    oi.quantity AS quantity,
    oi.unit_price_cents AS unit_price_cents,
    (oi.quantity * oi.unit_price_cents)::BIGINT AS line_total_cents,
    (oi.fulfilled_at IS NOT NULL) AS fulfilled
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.buyer_id = :user_id
ORDER BY o.created_at DESC, o.id DESC, oi.id
""",
        user_id=user_id,
    )

    return [
        {
            'order_id': row[0],
            'order_created_at': row[1],
            'product_id': row[2],
            'product_name': row[3],
            'quantity': row[4],
            'unit_price_cents': row[5],
            'line_total_cents': row[6],
            'fulfilled': bool(row[7]),
        }
        for row in rows
    ]
