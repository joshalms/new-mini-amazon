import time
from flask import current_app as app

_FEATURED_CACHE = {}

class Product:
    def __init__(self, id, name, price, available,
                 image_url=None, description=None,
                 average_rating=None):
        self.id = id
        self.name = name
        self.price = price
        self.available = available
        self.image_url = image_url
        self.description = description
        self.average_rating = average_rating

    @staticmethod
    def get(id):
        rows = app.db.execute('''
            SELECT p.id,
                   p.name,
                   p.price,
                   p.available,
                   p.image_url,
                   p.description,
                   AVG(pr.rating) AS average_rating,
            FROM Products p
            LEFT JOIN product_review pr ON pr.product_id = p.id
            WHERE p.id = :id
            GROUP BY p.id
        ''', id=id)
        return Product(*rows[0]) if rows else None

    @staticmethod
    def get_all(available=True):
        rows = app.db.execute('''
            SELECT p.id,
                   p.name,
                   p.price,
                   p.available,
                   p.image_url,
                   p.description,
                   AVG(pr.rating) AS average_rating,
            FROM Products p
            LEFT JOIN product_review pr ON pr.product_id = p.id
            WHERE p.available = :available
            GROUP BY p.id
            ORDER BY p.id
        ''', available=available)
        return [Product(*row) for row in rows]

    @staticmethod
    def get_top_k_expensive(k):
        rows = app.db.execute('''
            SELECT p.id,
                   p.name,
                   p.price,
                   p.available,
                   p.image_url,
                   p.description
            FROM Products p
            WHERE p.available = TRUE
            ORDER BY p.price DESC
            LIMIT :k
        ''', k=k)
        return [Product(*row, None, 0) for row in rows]

    @staticmethod
    def get_featured(limit=20):
        limit_val = max(1, min(100, int(limit)))
        cache_key = ('featured', limit_val)
        now = time.monotonic()
        cached = _FEATURED_CACHE.get(cache_key)

        if cached and cached['expires_at'] > now:
            return cached['rows']

        rows = app.db.execute('''
            SELECT p.id,
                   p.name,
                   p.price,
                   p.available,
                   p.image_url,
                   p.description,
                   AVG(pr.rating) AS average_rating,
            FROM Products p
            LEFT JOIN product_review pr ON pr.product_id = p.id
            WHERE p.available = TRUE
            GROUP BY p.id
            ORDER BY p.id
            LIMIT :limit
        ''', limit=limit_val)

        result = [Product(*row) for row in rows]
        _FEATURED_CACHE[cache_key] = {
            'rows': result,
            'expires_at': now + 60
        }
        return result
