from flask import current_app as app


def get_recent_reviews_for_seller(seller_id, limit=5):
    """Return recent reviews about a seller, newest first."""
    rows = app.db.execute(
        '''
SELECT sr.id,
       sr.user_id AS reviewer_id,
       u.full_name AS reviewer_name,
       sr.seller_id,
       sr.rating,
       sr.body,
       sr.created_at,
       sr.updated_at
FROM seller_review sr
JOIN users u ON u.id = sr.user_id
WHERE sr.seller_id = :seller_id
ORDER BY sr.created_at DESC
LIMIT :limit
''',
        seller_id=seller_id,
        limit=limit,
    )
    reviews = []
    for row in rows:
        reviews.append(
            {
                'id': row[0],
                'reviewer_id': row[1],
                'reviewer_name': row[2],
                'seller_id': row[3],
                'rating': row[4],
                'body': row[5],
                'created_at': row[6],
                'updated_at': row[7],
            }
        )
    return reviews


def get_summary_for_seller(seller_id):
    """Compute aggregate rating information for a seller."""
    rows = app.db.execute(
        '''
SELECT COUNT(*) AS review_count,
       AVG(rating) AS avg_rating,
       MIN(created_at) AS first_review_at,
       MAX(created_at) AS last_review_at
FROM seller_review
WHERE seller_id = :seller_id
''',
        seller_id=seller_id,
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
