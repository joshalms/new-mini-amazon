from flask import g, render_template
import datetime

from .models.product import Product
from .models import purchases

from flask import Blueprint
bp = Blueprint('index', __name__)


@bp.route('/')
def index():
    # get a limited set of available products for sale:
    products = Product.get_featured(limit=50)
    # find the products current user has bought:
    if g.get('user'):
        purchase_history = purchases.get_recent_line_items_for_user(
            g.user.id, limit=20)
    else:
        purchase_history = None
    # render the page by adding information to the index.html file
    return render_template('index.html',
                           avail_products=products,
                           purchase_history=purchase_history)
