from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user
def require_role(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role != role:
                flash('Permission denied', 'error')
                return redirect(url_for('main.dashboard'))
            return fn(*args, **kwargs)
        return wrapper
    return decorator
