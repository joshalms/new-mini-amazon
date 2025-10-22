import datetime

from flask import Blueprint, g, redirect, render_template, url_for
from humanize import naturaltime

from .models.wishlist import WishlistItem

bp = Blueprint('wishlist', __name__)


def humanize_time(dt):
    if dt is None:
        return ''
    return naturaltime(datetime.datetime.now() - dt)


@bp.route('/wishlist')
def wishlist():
    if not g.get('user'):
        return redirect(url_for('account.login'))
    items = WishlistItem.get_all_by_uid(g.user['id'])
    return render_template('wishlist.html',
                          items=items,
                          humanize_time=humanize_time)


@bp.route('/wishlist/add/<int:product_id>', methods=['POST'])
def wishlist_add(product_id):
    if not g.get('user'):
        return redirect(url_for('account.login'))
    WishlistItem.add(g.user['id'], product_id)
    return redirect(url_for('wishlist.wishlist'))
