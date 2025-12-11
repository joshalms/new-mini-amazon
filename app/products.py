from flask import Blueprint, request, jsonify, render_template, abort, g, url_for, current_app
from app.models.product import Product
from app.models import product_review
from app.models import purchases

bp = Blueprint('products', __name__)

@bp.route('/top-products')
def top_products():
    """
    Renders the Top Products page. (Now this page defaults to price_high ordering.)
    """
    return render_template('top_products.html')


@bp.route('/api/products/topk', methods=['GET'])
def top_k_products():
    """
    Returns the top-k most expensive products.
    Example: /api/products/topk?k=5
    (Still available, but UI now defaults to /api/products/filter?sort=price_high)
    """
    try:
        k = request.args.get('k', default=5, type=int)
        if k < 1:
            k = 1
        products = Product.get_top_k_expensive(k)
        output = []
        for p in products:
            # try to get average rating via product_review summary
            summary = product_review.get_summary_for_product(p.id) if hasattr(product_review, 'get_summary_for_product') else {}
            avg = None
            if summary:
                avg = summary.get('avg_rating') or summary.get('avg') or None
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "avg_rating": avg
            })
        return jsonify(output)
    except Exception as e:
        current_app.logger.exception("top_k_products error")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/products/search')
def search_products():
    """
    Search products by name substring (case-insensitive).
    Example: /api/products/search?q=Candy
    """
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify([])
        # Prefer a model-provided search; fallback to in-memory filter
        products = []
        if hasattr(Product, 'search_by_name'):
            products = Product.search_by_name(q)
        else:
            # fallback: get all and filter (case-insensitive)
            allp = Product.get_all() if hasattr(Product, 'get_all') else []
            qlow = q.lower()
            products = [p for p in allp if qlow in (p.name or '').lower()]

        output = []
        for p in products:
            summary = product_review.get_summary_for_product(p.id) if hasattr(product_review, 'get_summary_for_product') else {}
            avg = summary.get('avg') or summary.get('avg_rating') or None
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "avg_rating": avg
            })
        return jsonify(output)
    except Exception as e:
        current_app.logger.exception("search_products error")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/products/filter')
def filter_products():
    """
    Return products sorted/filtered by a `sort` param:
      sort = price_high | price_low | az | za | rating
    Example: /api/products/filter?sort=rating
    """
    try:
        sort = request.args.get('sort', 'price_high')
        # Fetch products; assume Product.get_all exists
        products = Product.get_all() if hasattr(Product, 'get_all') else []

        # Precompute avg ratings map to allow sorting by rating
        avg_map = {}
        if sort == 'rating' or True:
            # we can compute ratings for all products (used for output too)
            for p in products:
                summary = product_review.get_summary_for_product(p.id) if hasattr(product_review, 'get_summary_for_product') else {}
                avg = summary.get('avg') or summary.get('avg_rating') or None
                try:
                    avg_map[p.id] = float(avg) if avg is not None else None
                except Exception:
                    avg_map[p.id] = None

        # sorting
        if sort == "az":
            products = sorted(products, key=lambda p: (p.name or '').lower())
        elif sort == "za":
            products = sorted(products, key=lambda p: (p.name or '').lower(), reverse=True)
        elif sort == "price_low":
            products = sorted(products, key=lambda p: float(p.price) if p.price is not None else 0)
        elif sort == "price_high":
            products = sorted(products, key=lambda p: float(p.price) if p.price is not None else 0, reverse=True)
        elif sort == "rating":
            # sort by average rating (None -> -inf or push last)
            products = sorted(products, key=lambda p: (avg_map.get(p.id) is None, -(avg_map.get(p.id) or 0)))

        output = []
        for p in products:
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "avg_rating": avg_map.get(p.id)
            })
        return jsonify(output)
    except Exception as e:
        current_app.logger.exception("filter_products error")
        return jsonify({"error": str(e)}), 500


@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    """Simple product detail page (if not present elsewhere)."""
    product = Product.get(product_id) if hasattr(Product, 'get') else None
    if not product:
        abort(404)
    return render_template('product_detail.html', product=product)

@bp.route('/products/<int:product_id>/reviews')
def product_reviews(product_id):
    product = Product.get(product_id)
    if not product:
        abort(404)
    reviews = product_review.get_recent_reviews_for_product(product_id)
    return render_template("product_reviews.html",
                           product=product,
                           reviews=reviews)
    

