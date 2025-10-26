from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import purchases
from app.models.user import User


bp = Blueprint('account', __name__)


@bp.before_app_request
def attach_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
        return

    user = User.get(user_id)
    if user is None:
        session.clear()
        g.user = None
        return

    g.user = user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('account.login', next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _format_money(cents):
    try:
        return f"${cents / 100:.2f}"
    except (TypeError, ValueError):
        return "$0.00"


@bp.app_context_processor
def inject_helpers():
    return {'format_money': _format_money}


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect(url_for('account.account_home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        address = request.form.get('address', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        errors = []
        if not email:
            errors.append('Email is required.')
        if not full_name:
            errors.append('Full name is required.')
        if not address:
            errors.append('Address is required.')
        if not password:
            errors.append('Password is required.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'account/register.html',
                email=email,
                full_name=full_name,
                address=address,
            )

        try:
            user = User.create(email, full_name, address, password)
        except IntegrityError:
            flash('Email is already registered.', 'error')
            return render_template(
                'account/register.html',
                email=email,
                full_name=full_name,
                address=address,
            )

        with current_app.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO account_balance (user_id, balance_cents)
                    VALUES (:user_id, 0)
                    ON CONFLICT (user_id) DO NOTHING
                    """
                ),
                {'user_id': user.id},
            )

        session.clear()
        session['user_id'] = user.id
        flash('Welcome! Your account has been created.', 'success')
        return redirect(url_for('account.account_home'))

    return render_template('account/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('account.account_home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('account/login.html', email=email)

        user = User.authenticate(email, password)
        if not user:
            flash('Invalid email or password.', 'error')
            return render_template('account/login.html', email=email)

        session.clear()
        session['user_id'] = user.id
        flash('Logged in successfully.', 'success')
        next_url = request.args.get('next')
        return redirect(next_url or url_for('account.account_home'))

    return render_template('account/login.html')


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('account.login'))


@bp.route('/account')
@login_required
def account_home():
    balance_cents = User.get_balance(g.user.id)
    return render_template(
        'account/account.html',
        user=g.user,
        balance_cents=balance_cents,
    )


@bp.route('/account/edit', methods=['GET', 'POST'])
@login_required
def account_edit():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        address = request.form.get('address', '').strip()
        new_password = request.form.get('new_password', '')

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not address:
            errors.append('Address is required.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('account/account_edit.html', user=g.user)

        User.update_profile(g.user.id, full_name, address)
        g.user.full_name = full_name
        g.user.address = address

        if new_password:
            User.update_password(g.user.id, new_password)
            flash('Password updated.', 'success')

        flash('Profile updated.', 'success')
        return redirect(url_for('account.account_home'))

    return render_template('account/account_edit.html', user=g.user)


@bp.route('/account/balance', methods=['GET', 'POST'])
@login_required
def account_balance():
    if request.method == 'POST':
        action = request.form.get('action')
        amount_raw = request.form.get('amount_dollars', '').strip()

        try:
            amount_dollars = int(amount_raw)
        except (TypeError, ValueError):
            flash('Enter a whole dollar amount.', 'error')
            return redirect(url_for('account.account_balance'))

        if amount_dollars <= 0:
            flash('Amount must be positive.', 'error')
            return redirect(url_for('account.account_balance'))

        delta_cents = amount_dollars * 100
        note = ''

        if action == 'topup':
            note = 'Top up'
        elif action == 'withdraw':
            delta_cents = -delta_cents
            note = 'Withdraw'
        else:
            flash('Select an action.', 'error')
            return redirect(url_for('account.account_balance'))

        try:
            User.adjust_balance(g.user.id, delta_cents, note)
            flash('Balance updated.', 'success')
        except ValueError:
            flash('Withdrawal would make balance negative.', 'error')

        return redirect(url_for('account.account_balance'))

    balance_cents = User.get_balance(g.user.id)
    history = User.get_balance_history(g.user.id)
    return render_template(
        'account/balance.html',
        balance_cents=balance_cents,
        history=history,
    )


@bp.route('/account/purchases')
@login_required
def account_purchases():
    purchase_rows = purchases.get_purchases_for_user(g.user.id)
    return render_template('account/purchases.html', purchases=purchase_rows)


@bp.route('/api/users/<int:user_id>/purchases')
def api_user_purchases(user_id):
    """TODO: restrict to the owning user or admins in production."""
    purchase_rows = purchases.get_purchases_for_user(user_id)
    serialized = [
        {
            **row,
            'order_created_at': row['order_created_at'].isoformat()
            if row['order_created_at']
            else None,
        }
        for row in purchase_rows
    ]
    return jsonify(serialized)


@bp.route('/users/<int:user_id>')
def public_profile(user_id):
    user = User.get(user_id)
    if user is None:
        abort(404)

    return render_template('account/public_user.html', user=user)
