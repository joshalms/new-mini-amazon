from flask import current_app as app


def get_purchases_for_user(user_id):
    rows = app.db.execute(
        """
SELECT
    o.id AS order_id,
    o.created_at AS order_created_at,
    o.total_cents AS total_cents,
    COALESCE(SUM(oi.quantity), 0) AS item_count,
    COALESCE(BOOL_AND(oi.fulfilled_at IS NOT NULL), FALSE) AS all_fulfilled
FROM orders o
LEFT JOIN order_items oi ON oi.order_id = o.id
WHERE o.buyer_id = :user_id
GROUP BY o.id, o.created_at, o.total_cents
ORDER BY o.created_at DESC
""",
        user_id=user_id,
    )

    return [
        {
            'order_id': row[0],
            'order_created_at': row[1],
            'total_cents': row[2],
            'item_count': row[3],
            'fulfilled': bool(row[4]),
        }
        for row in rows
    ]
