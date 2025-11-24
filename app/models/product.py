from flask import current_app as app


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

