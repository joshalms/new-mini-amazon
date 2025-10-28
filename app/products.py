from flask import Blueprint, request, jsonify, render_template
from app.models.product import Product

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
        k = request.args.get('k', default=1, type=int)
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
