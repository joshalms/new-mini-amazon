from flask import Blueprint, request, jsonify
from app.models.product import Product

bp = Blueprint('products', __name__)

@bp.route('/api/products/topk', methods=['GET'])
def top_k_products():
    """
    Returns the top-k most expensive products.
    Example: /api/products/topk?k=5
    """
    k = request.args.get('k', default=5, type=int)
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
