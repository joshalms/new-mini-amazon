from flask import current_app as app
from sqlalchemy import text


def get_recent_reviews_for_product(product_id, limit=5):
    """Return recent reviews about a product, newest first."""
    rows = app.db.execute(
        '''
SELECT pr.id,
       pr.user_id AS reviewer_id,
       u.full_name AS reviewer_name,
       pr.product_id,
       pr.rating,
       pr.body,
       pr.created_at,
       pr.updated_at
FROM product_review pr
JOIN users u ON u.id = pr.user_id
WHERE pr.product_id = :product_id
ORDER BY pr.created_at DESC
LIMIT :limit
''',
        product_id=product_id,
        limit=limit,
    )
    reviews = []
    for row in rows:
        reviews.append(
            {
                'id': row[0],
                'reviewer_id': row[1],
                'reviewer_name': row[2],
                'product_id': row[3],
                'rating': row[4],
                'body': row[5],
                'created_at': row[6],
                'updated_at': row[7],
            }
        )
    return reviews


def get_summary_for_product(product_id):
    """Compute aggregate rating information for a product."""
    rows = app.db.execute(
        '''
SELECT COUNT(*) AS review_count,
       AVG(rating) AS avg_rating,
       MIN(created_at) AS first_review_at,
       MAX(created_at) AS last_review_at
FROM product_review
WHERE product_id = :product_id
''',
        product_id=product_id,
    )
    if not rows:
        return {
            'review_count': 0,
            'average_rating': None,
            'first_review_at': None,
            'last_review_at': None,
        }

    row = rows[0]
    avg_rating = float(row[1]) if row[1] is not None else None
    return {
        'review_count': row[0] or 0,
        'average_rating': avg_rating,
        'first_review_at': row[2],
        'last_review_at': row[3],
    }


def get_user_review_for_product(user_id, product_id):
    """Get a specific user's review for a product, if it exists."""
    rows = app.db.execute(
        '''
SELECT pr.id,
       pr.user_id,
       pr.product_id,
       pr.rating,
       pr.body,
       pr.created_at,
       pr.updated_at
FROM product_review pr
WHERE pr.user_id = :user_id AND pr.product_id = :product_id
''',
        user_id=user_id,
        product_id=product_id,
    )
    if not rows:
        return None

    row = rows[0]
    return {
        'id': row[0],
        'user_id': row[1],
        'product_id': row[2],
        'rating': row[3],
        'body': row[4],
        'created_at': row[5],
        'updated_at': row[6],
    }


def create_review(user_id, product_id, rating, body):
    """Create a new product review."""
    with app.db.engine.begin() as conn:
        result = conn.execute(
            text(
                '''
INSERT INTO product_review (user_id, product_id, rating, body)
VALUES (:user_id, :product_id, :rating, :body)
RETURNING id, created_at, updated_at
'''
            ),
            {'user_id': user_id, 'product_id': product_id, 'rating': rating, 'body': body},
        ).first()
        return {
            'id': result[0],
            'user_id': user_id,
            'product_id': product_id,
            'rating': rating,
            'body': body,
            'created_at': result[1],
            'updated_at': result[2],
        }


def update_review(review_id, rating, body):
    """Update an existing product review."""
    with app.db.engine.begin() as conn:
        result = conn.execute(
            text(
                '''
UPDATE product_review
SET rating = :rating, body = :body, updated_at = NOW()
WHERE id = :review_id
RETURNING id, user_id, product_id, rating, body, created_at, updated_at
'''
            ),
            {'review_id': review_id, 'rating': rating, 'body': body},
        ).first()
        if not result:
            return None
        return {
            'id': result[0],
            'user_id': result[1],
            'product_id': result[2],
            'rating': result[3],
            'body': result[4],
            'created_at': result[5],
            'updated_at': result[6],
        }


def delete_review(review_id):
    """Delete a product review."""
    with app.db.engine.begin() as conn:
        result = conn.execute(
            text('DELETE FROM product_review WHERE id = :review_id RETURNING id'),
            {'review_id': review_id},
        ).first()
        return result is not None
