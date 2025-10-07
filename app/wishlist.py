import datetime

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user
from humanize import naturaltime

from .models.wishlist import WishlistItem

bp = Blueprint('wishlist', __name__)


def humanize_time(dt):
    if dt is None:
        return ''
    return naturaltime(datetime.datetime.now() - dt)


@bp.route('/wishlist')
def wishlist():
    if not current_user.is_authenticated:
        return redirect(url_for('users.login'))
    items = WishlistItem.get_all_by_uid(current_user.id)
    return render_template('wishlist.html',
                          items=items,
                          humanize_time=humanize_time)


@bp.route('/wishlist/add/<int:product_id>', methods=['POST'])
def wishlist_add(product_id):
    if not current_user.is_authenticated:
        return redirect(url_for('users.login'))
    WishlistItem.add(current_user.id, product_id)
    return redirect(url_for('wishlist.wishlist'))
