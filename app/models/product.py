
import time
from flask import current_app as app


_FEATURED_CACHE = {}


class Product:
    def __init__(self, id, name, price, available, average_rating=None):
        self.id = id
        self.name = name
        self.price = price
        self.available = available
        self.average_rating = average_rating

    @staticmethod
    def get(id):
        rows = app.db.execute('''
SELECT id, name, price, available
FROM Products
WHERE id = :id
''',
                              id=id)
        return Product(*(rows[0])) if rows is not None else None

    @staticmethod
    def get_all(available=True):
        rows = app.db.execute('''
SELECT p.id, p.name, p.price, p.available, AVG(pr.rating) AS average_rating
FROM Products p
LEFT JOIN product_review pr ON pr.product_id = p.id
WHERE p.available = :available
GROUP BY p.id, p.name, p.price, p.available
ORDER BY p.id
''',
                              available=available)
        return [Product(*row) for row in rows]

    @staticmethod
    def get_top_k_expensive(k):
        rows = app.db.execute('''
SELECT id, name, price, available
FROM Products
WHERE available = TRUE
ORDER BY price DESC
LIMIT :k
''', k=k)
        return [Product(*row) for row in rows]

    @staticmethod
    def get_featured(limit=20):
        """Lightweight fetch for the front page that avoids full counts."""
        try:
            limit_val = int(limit)
        except (TypeError, ValueError):
            limit_val = 20
        limit_val = max(1, min(100, limit_val))

        cache_key = ('featured', limit_val)
        now = time.monotonic()
        cached = _FEATURED_CACHE.get(cache_key)
        if cached and cached['expires_at'] > now:
            return cached['rows']

        rows = app.db.execute(
            '''
SELECT p.id, p.name, p.price, p.available, AVG(pr.rating) AS average_rating
FROM Products p
LEFT JOIN product_review pr ON pr.product_id = p.id
WHERE p.available = TRUE
GROUP BY p.id, p.name, p.price, p.available
ORDER BY p.id
LIMIT :limit
''',
            limit=limit_val,
        )
        result = [Product(*row) for row in rows]
        _FEATURED_CACHE[cache_key] = {
            'rows': result,
            'expires_at': now + 60,  # small cache to reduce repeat homepage hits
        }
        return result
