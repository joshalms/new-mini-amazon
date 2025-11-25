from flask import Blueprint, request, jsonify, render_template, abort
from app.models.product import Product
from app.models import product_review

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
    """
    Display all reviews for a product.
    """
    product = Product.get(product_id)
    if not product:
        abort(404)

    reviews = product_review.get_recent_reviews_for_product(product_id, limit=100)
    summary = product_review.get_summary_for_product(product_id)

    return render_template(
        'product_reviews.html',
        product=product,
        reviews=reviews,
        summary=summary,
    )
