from datetime import datetime, timedelta, timezone
from functools import wraps
from bson import ObjectId
from flask import current_app, g, jsonify, request
import jwt


def serialize_id(value):
    return str(value) if isinstance(value, ObjectId) else value


def token_for(user):
    now = datetime.now(timezone.utc)
    payload = {'sub': str(user['_id']), 'iat': now, 'exp': now + timedelta(hours=current_app.config['TOKEN_TTL_HOURS'])}
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def require_auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        token = header[7:].strip() if header.lower().startswith('bearer ') else ''
        if not token:
            return jsonify(error='Authentication required'), 401
        try:
            payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            user = current_app.extensions['pymongo'].db.users.find_one({'_id': ObjectId(payload['sub']), 'active': True})
        except (jwt.PyJWTError, ValueError, KeyError):
            user = None
        if not user:
            return jsonify(error='Invalid or expired token'), 401
        g.user = user
        return fn(*args, **kwargs)
    return wrapped


def require_admin(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if g.user.get('role') != 'admin':
            return jsonify(error='Administrator role required'), 403
        return fn(*args, **kwargs)
    return wrapped
