from flask import Blueprint, request, jsonify, render_template, abort, g, url_for
from app.models.product import Product
from app.models import product_review
from app.models import purchases

bp = Blueprint('products', __name__)

@bp.route('/top-products')
def top_products():
    """
    Renders the Top Products page.
    """
    return render_template('top_products.html')


@bp.route('/api/products/topk', methods=['GET'])
def top_k_products():
    """
    Returns the top-k most expensive products.
    Example: /api/products/topk?k=5
    """
    try:
        k = request.args.get('k', default=5, type=int)
        if k < 1:
            k = 1
        products = Product.get_top_k_expensive(k)
        return jsonify([
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available
            }
            for p in products
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/products/<int:product_id>/reviews')
def product_reviews(product_id):
    """Display all reviews for a product with sorting options."""
    product = Product.get(product_id)
    if not product:
        abort(404)

    sort = request.args.get('sort', 'date')
    reviews = product_review.get_recent_reviews_for_product(product_id, limit=100, sort=sort)
    summary = product_review.get_summary_for_product(product_id)

    # check if logged-in user can review this product
    user_review = None
    review_url = None
    can_review = False
    user_votes = {}

    if g.user:
        user_review = product_review.get_user_review_for_product(g.user.id, product_id)
        order_info = purchases.get_user_order_with_product(g.user.id, product_id)
        if order_info:
            can_review = True
            review_url = url_for(
                'account.review_product',
                order_id=order_info['order_id'],
                product_id=product_id,
            )
        user_votes = product_review.get_user_votes_for_product(g.user.id, product_id)

    return render_template(
        'product_reviews.html',
        product=product,
        reviews=reviews,
        summary=summary,
        current_sort=sort,
        user_review=user_review,
        review_url=review_url,
        can_review=can_review,
        user_votes=user_votes,
    )
    
@bp.route('/api/products/search')
def search_products():
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([])

    products = Product.search_by_name(query)  # You may need to implement this

    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "available": p.available
        }
        for p in products
    ])
    
@bp.route('/api/products/filter')
def filter_products():
    sort = request.args.get('sort', 'az')

    products = Product.get_all()  # or your actual method

    if sort == "az":
        products = sorted(products, key=lambda p: p.name)
    elif sort == "za":
        products = sorted(products, key=lambda p: p.name, reverse=True)
    elif sort == "price_low":
        products = sorted(products, key=lambda p: p.price)
    elif sort == "price_high":
        products = sorted(products, key=lambda p: p.price, reverse=True)
    elif sort == "rating":
        products = sorted(products, key=lambda p: p.avg_rating or 0, reverse=True)

    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "available": p.available
        }
        for p in products
    ])

@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    product = Product.get(product_id)
    if not product:
        abort(404)
    return render_template("product_detail.html", product=product)

