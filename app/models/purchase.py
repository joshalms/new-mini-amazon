from flask import current_app as app


class Purchase:
    """Legacy helper that now reflects canonical orders/order_items data."""

    def __init__(self, id, uid, pid, time_purchased):
        self.id = id
        self.uid = uid
        self.pid = pid
        self.time_purchased = time_purchased

    @staticmethod
    def get(id):
        rows = app.db.execute(
            '''
SELECT oi.id, o.buyer_id AS uid, oi.product_id AS pid, o.created_at AS time_purchased
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
WHERE oi.id = :id
''',
            id=id,
        )
        return Purchase(*(rows[0])) if rows else None

    @staticmethod
    def get_all_by_uid_since(uid, since):
        rows = app.db.execute(
            '''
SELECT oi.id, o.buyer_id AS uid, oi.product_id AS pid, o.created_at AS time_purchased
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.buyer_id = :uid
  AND o.created_at >= :since
ORDER BY o.created_at DESC, o.id DESC, oi.id DESC
''',
            uid=uid,
            since=since,
        )
        return [Purchase(*row) for row in rows]
