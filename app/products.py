from flask import Blueprint, request, jsonify, render_template, abort, current_app
from app.models.product import Product
from app.models import product_review
from app.models import purchases

bp = Blueprint('products', __name__)

@bp.route('/top-products')
def top_products():
    """
    Renders the Top Products page. (UI defaults to /api/products/filter?sort=price_high)
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

        products = Product.get_top_k_expensive(k) if hasattr(Product, 'get_top_k_expensive') else (Product.get_all()[:k] if hasattr(Product, 'get_all') else [])

        output = []
        for p in products:
            # try to get average rating via product_review summary
            summary = product_review.get_summary_for_product(p.id) if hasattr(product_review, 'get_summary_for_product') else {}
            avg = summary.get('avg_rating') or summary.get('avg') or getattr(p, 'average_rating', None)
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "image_url": getattr(p, "image_url", None),
                "description": getattr(p, "description", None),
                "avg_rating": avg,
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

        products = []
        if hasattr(Product, 'search_by_name'):
            products = Product.search_by_name(q)
        else:
            allp = Product.get_all(available=True) if hasattr(Product, 'get_all') else []
            qlow = q.lower()
            products = [p for p in allp if qlow in (p.name or '').lower()]

        output = []
        for p in products:
            summary = product_review.get_summary_for_product(p.id) if hasattr(product_review, 'get_summary_for_product') else {}
            avg = summary.get('avg') or summary.get('avg_rating') or getattr(p, 'average_rating', None)
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "image_url": getattr(p, "image_url", None),
                "description": getattr(p, "description", None),
                "avg_rating": avg,
            })
        return jsonify(output)
    except Exception as e:
        current_app.logger.exception("search_products error")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/products/available')
def available_products():
    """
    Return only available products (used by frontend 'Available Only').
    """
    try:
        # Prefer model helper if exists
        if hasattr(Product, 'get_all'):
            products = Product.get_all(available=True)
        else:
            products = [p for p in (Product.get_all() if hasattr(Product, 'get_all') else []) if p.available]

        output = []
        for p in products:
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "image_url": getattr(p, "image_url", None),
                "description": getattr(p, "description", None),
                "avg_rating": getattr(p, "average_rating", None),
            })
        return jsonify(output)
    except Exception as e:
        current_app.logger.exception("available_products error")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/products/filter')
def filter_products():
    """
    Return products sorted/filtered by a `sort` param:
      sort = price_high | price_low | az | za | rating | available_only | availability
    Example: /api/products/filter?sort=rating
    """
    try:
        sort = request.args.get('sort', 'price_high')

        # Fetch products from model (default to get_all True if available param)
        if hasattr(Product, 'get_all'):
            # default show all available products for list endpoints unless explicitly intended otherwise
            products = Product.get_all(available=True)
        else:
            products = []

        # Precompute avg ratings map used for sorting by rating and for output
        avg_map = {}
        for p in products:
            summary = product_review.get_summary_for_product(p.id) if hasattr(product_review, 'get_summary_for_product') else {}
            avg = summary.get('avg') or summary.get('avg_rating') or getattr(p, 'average_rating', None)
            try:
                avg_map[p.id] = float(avg) if avg is not None else None
            except Exception:
                avg_map[p.id] = None

        # Sorting & Filtering
        if sort == "az":
            products = sorted(products, key=lambda p: (p.name or '').lower())
        elif sort == "za":
            products = sorted(products, key=lambda p: (p.name or '').lower(), reverse=True)
        elif sort == "price_low":
            products = sorted(products, key=lambda p: float(p.price) if p.price is not None else 0)
        elif sort == "price_high":
            products = sorted(products, key=lambda p: float(p.price) if p.price is not None else 0, reverse=True)
        elif sort == "rating":
            products = sorted(products, key=lambda p: (avg_map.get(p.id) is None, -(avg_map.get(p.id) or 0)))
        elif sort == "available_only":
            products = [p for p in products if p.available]
        elif sort == "availability":
            # In-stock first, tiebreaker by name
            products = sorted(products, key=lambda p: (not p.available, (p.name or '').lower()))
        else:
            # default fallback: price_high
            products = sorted(products, key=lambda p: float(p.price) if p.price is not None else 0, reverse=True)

        # Build JSON output
        output = []
        for p in products:
            output.append({
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "available": p.available,
                "image_url": getattr(p, "image_url", None),
                "description": getattr(p, "description", None),
                "avg_rating": avg_map.get(p.id),
            })
        return jsonify(output)
    except Exception as e:
        current_app.logger.exception("filter_products error")
        return jsonify({"error": str(e)}), 500


@bp.route('/products/<int:product_id>')
def product_detail(product_id):
    """Simple product detail page (uses Product.get which now returns image & description)"""
    product = Product.get(product_id) if hasattr(Product, 'get') else None
    if not product:
        abort(404)
    return render_template('product_detail.html', product=product)


@bp.route('/products/<int:product_id>/reviews')
def product_reviews(product_id):
    product = Product.get(product_id) if hasattr(Product, 'get') else None
    if not product:
        abort(404)
    reviews = product_review.get_recent_reviews_for_product(product_id) if hasattr(product_review, 'get_recent_reviews_for_product') else []
    return render_template("product_reviews.html", product=product, reviews=reviews)
