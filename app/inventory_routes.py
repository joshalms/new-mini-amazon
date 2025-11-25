from flask import Blueprint, jsonify, request, render_template
from app.models.inventory import get_inventory_for_user

bp = Blueprint('inventory', __name__)

@bp.route('/api/users/<int:user_id>/inventory', methods=['GET'])
def api_get_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return jsonify({"user_id": user_id, "items": items})


@bp.route('/users/<int:user_id>/inventory')
def view_inventory(user_id):
    items = get_inventory_for_user(user_id)
    return render_template('inventory.html', inventory=items, owner_id=user_id)
