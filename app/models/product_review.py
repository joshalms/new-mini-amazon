from flask import current_app as app
from sqlalchemy import text


def get_recent_reviews_for_product(product_id, limit=5, sort='date', top_helpful=3):
    """Return reviews about a product with vote counts.

    By default shows top 3 most helpful first, then remaining by date.
    Helpfulness score = upvotes - downvotes.
    """
    if sort == 'rating':
        order_clause = 'pr.rating DESC, pr.created_at DESC'
    elif sort == 'helpful':
        order_clause = 'helpful_score DESC, pr.created_at DESC'
    else:
        # default: top N helpful first, then by date
        order_clause = f'''
            CASE WHEN row_num <= {int(top_helpful)} THEN 0 ELSE 1 END,
            CASE WHEN row_num <= {int(top_helpful)} THEN helpful_score END DESC,
            pr.created_at DESC
        '''

    rows = app.db.execute(
        f'''
WITH review_votes AS (
    SELECT pr.id,
           pr.user_id AS reviewer_id,
           u.full_name AS reviewer_name,
           pr.product_id,
           pr.rating,
           pr.body,
           pr.created_at,
           pr.updated_at,
           COALESCE(v.upvotes, 0) AS upvotes,
           COALESCE(v.downvotes, 0) AS downvotes,
           COALESCE(v.upvotes, 0) - COALESCE(v.downvotes, 0) AS helpful_score,
           ROW_NUMBER() OVER (ORDER BY COALESCE(v.upvotes, 0) - COALESCE(v.downvotes, 0) DESC, pr.created_at DESC) AS row_num
    FROM product_review pr
    JOIN users u ON u.id = pr.user_id
    LEFT JOIN (
        SELECT review_id,
               SUM(CASE WHEN vote_value = 1 THEN 1 ELSE 0 END) AS upvotes,
               SUM(CASE WHEN vote_value = -1 THEN 1 ELSE 0 END) AS downvotes
        FROM product_review_vote
        GROUP BY review_id
    ) v ON v.review_id = pr.id
    WHERE pr.product_id = :product_id
)
SELECT id, reviewer_id, reviewer_name, product_id, rating, body,
       created_at, updated_at, upvotes, downvotes, helpful_score, row_num
FROM review_votes pr
ORDER BY {order_clause}
LIMIT :limit
''',
        product_id=product_id,
        limit=limit,
    )
    reviews = []
    for row in rows:
        reviews.append({
            'id': row[0],
            'reviewer_id': row[1],
            'reviewer_name': row[2],
            'product_id': row[3],
            'rating': row[4],
            'body': row[5],
            'created_at': row[6],
            'updated_at': row[7],
            'upvotes': row[8],
            'downvotes': row[9],
            'helpful_score': row[10],
        })
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


def get_review_by_id(review_id):
    """Get a review by its id."""
    rows = app.db.execute(
        '''
SELECT id, user_id, product_id, rating, body, created_at, updated_at
FROM product_review
WHERE id = :review_id
''',
        review_id=review_id,
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


def get_reviews_by_user(user_id, sort='date'):
    """Get all product reviews by a user, with product info."""
    order_clause = 'pr.created_at DESC'
    if sort == 'rating':
        order_clause = 'pr.rating DESC, pr.created_at DESC'

    rows = app.db.execute(
        f'''
SELECT pr.id,
       pr.user_id,
       pr.product_id,
       p.name AS product_name,
       pr.rating,
       pr.body,
       pr.created_at,
       pr.updated_at
FROM product_review pr
JOIN products p ON p.id = pr.product_id
WHERE pr.user_id = :user_id
ORDER BY {order_clause}
''',
        user_id=user_id,
    )
    reviews = []
    for row in rows:
        reviews.append({
            'id': row[0],
            'user_id': row[1],
            'product_id': row[2],
            'product_name': row[3],
            'rating': row[4],
            'body': row[5],
            'created_at': row[6],
            'updated_at': row[7],
        })
    return reviews


def set_vote(user_id, review_id, vote_value):
    """Set user's vote on a review. vote_value: 1=upvote, -1=downvote, 0=remove."""
    with app.db.engine.begin() as conn:
        if vote_value == 0:
            conn.execute(
                text('''
DELETE FROM product_review_vote
WHERE user_id = :user_id AND review_id = :review_id
'''),
                {'user_id': user_id, 'review_id': review_id},
            )
        else:
            conn.execute(
                text('''
INSERT INTO product_review_vote (user_id, review_id, vote_value)
VALUES (:user_id, :review_id, :vote_value)
ON CONFLICT (user_id, review_id)
DO UPDATE SET vote_value = :vote_value, created_at = NOW()
'''),
                {'user_id': user_id, 'review_id': review_id, 'vote_value': vote_value},
            )


def get_user_vote(user_id, review_id):
    """Get user's vote on a review. Returns 1, -1, or 0 (no vote)."""
    rows = app.db.execute(
        '''
SELECT vote_value FROM product_review_vote
WHERE user_id = :user_id AND review_id = :review_id
''',
        user_id=user_id,
        review_id=review_id,
    )
    return rows[0][0] if rows else 0


def get_user_votes_for_product(user_id, product_id):
    """Get dict of review_id -> vote_value for a product."""
    rows = app.db.execute(
        '''
SELECT v.review_id, v.vote_value
FROM product_review_vote v
JOIN product_review pr ON pr.id = v.review_id
WHERE v.user_id = :user_id AND pr.product_id = :product_id
''',
        user_id=user_id,
        product_id=product_id,
    )
    return {row[0]: row[1] for row in rows}


def get_vote_counts(review_id):
    """Get upvote and downvote counts for a review."""
    rows = app.db.execute(
        '''
SELECT
    SUM(CASE WHEN vote_value = 1 THEN 1 ELSE 0 END) AS upvotes,
    SUM(CASE WHEN vote_value = -1 THEN 1 ELSE 0 END) AS downvotes
FROM product_review_vote
WHERE review_id = :review_id
''',
        review_id=review_id,
    )
    if rows and rows[0][0] is not None:
        return {'upvotes': rows[0][0], 'downvotes': rows[0][1]}
    return {'upvotes': 0, 'downvotes': 0}
