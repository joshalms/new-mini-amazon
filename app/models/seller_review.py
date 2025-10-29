from flask import current_app as app

def get_recent_by_user_id(user_id, limit=5):
    rows = app.db.execute(
        '''
SELECT id, user_id, seller_id, rating, body, created_at, updated_at
FROM seller_review
WHERE user_id = :user_id
ORDER BY created_at DESC
LIMIT :limit
''',
        user_id=user_id,
        limit=limit,
    )

    reviews = []
    for row in rows:
        id, user_id, seller_id, rating, body, created_at, updated_at = row
        reviews.append({
            'id': id,
            'user_id': user_id,
            'seller_id': seller_id,
            'rating': rating,
            'body': body,
            'created_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
            'updated_at': updated_at.isoformat() if hasattr(updated_at, 'isoformat') else updated_at,
        })
    return reviews
