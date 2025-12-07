import secrets

from flask import Flask, abort, request, session

from .config import Config
from .db import DB
from flask_cors import CORS


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.db = DB(app)

    def _generate_csrf_token():
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_hex(16)
            session['_csrf_token'] = token
        return token

    def _protect_csrf():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            content_type = (request.content_type or '').lower()
            if content_type.startswith('application/json'):
                return
            token = session.get('_csrf_token')
            submitted = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            if not token or not submitted or token != submitted:
                abort(400)

    app.before_request(_protect_csrf)
    app.jinja_env.globals['csrf_token'] = _generate_csrf_token

    from .account import bp as account_bp
    app.register_blueprint(account_bp)

    from .wishlist import bp as wishlist_bp
    app.register_blueprint(wishlist_bp)

    from .index import bp as index_bp
    app.register_blueprint(index_bp)
    
    from .products import bp as product_bp
    app.register_blueprint(product_bp)


    from .cart_routes import bp as cart_bp
    app.register_blueprint(cart_bp)

    from .inventory_routes import bp as inventory_bp
    app.register_blueprint(inventory_bp)

    from .users import routes as users_routes
    app.register_blueprint(users_routes.bp)

    return app
