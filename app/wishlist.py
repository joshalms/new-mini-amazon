from flask import Blueprint, jsonify, redirect, url_for
from flask_login import current_user

from .models.wishlist import WishlistItem

bp = Blueprint('wishlist', __name__)


@bp.route('/wishlist')
def wishlist():
    if not current_user.is_authenticated:
        return jsonify({}), 404
    items = WishlistItem.get_all_by_uid(current_user.id)
    return jsonify([item.to_dict() for item in items])


@bp.route('/wishlist/add/<int:product_id>', methods=['POST'])
def wishlist_add(product_id):
    if not current_user.is_authenticated:
        return jsonify({}), 404
    WishlistItem.add(current_user.id, product_id)
    return redirect(url_for('wishlist.wishlist'))
