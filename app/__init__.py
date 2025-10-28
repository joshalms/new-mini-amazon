from flask import Flask

from .config import Config
from .db import DB
from flask_cors import CORS


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.db = DB(app)

    from .account import bp as account_bp
    app.register_blueprint(account_bp)

    from .wishlist import bp as wishlist_bp
    app.register_blueprint(wishlist_bp)

    from .index import bp as index_bp
    app.register_blueprint(index_bp)

    from .cart_routes import bp as cart_bp
    app.register_blueprint(cart_bp)

    from .inventory_routes import bp as inventory_bp
    app.register_blueprint(inventory_bp)

    return app
