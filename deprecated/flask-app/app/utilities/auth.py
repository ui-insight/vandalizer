"""Authentication utilities for API token-based access."""

from functools import wraps
from flask import request, jsonify
from app.models import User


def token_required(f):
    """Decorator for routes that accept API token authentication.

    The token can be provided in two ways:
    1. Authorization header: "Bearer <token>"
    2. Query parameter: ?token=<token>

    The authenticated user is passed to the route function as 'auth_user' kwarg.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        # Check Authorization header first
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Fall back to query parameter (useful for WebSocket upgrades)
        if not token and 'token' in request.args:
            token = request.args.get('token')

        if not token:
            return jsonify({'error': 'Authentication token is missing'}), 401

        # Look up user by token
        user = User.objects(api_token=token).first()

        if not user:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # Inject authenticated user into route function
        kwargs['auth_user'] = user
        return f(*args, **kwargs)

    return decorated_function


def get_user_from_token(token: str) -> User | None:
    """Get user from API token. Returns None if token is invalid."""
    if not token:
        return None
    return User.objects(api_token=token).first()
