from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo.errors import DuplicateKeyError
from ..db import mongo
from ..models import now_utc, user_public
from ..utils import token_for

auth_bp = Blueprint('auth', __name__)


@auth_bp.post('/auth/register')
def register():
    body = request.get_json(silent=True) or {}
    name, email, password = (str(body.get(k, '')).strip() for k in ('name', 'email', 'password'))
    division = str(body.get('division', '')).strip()
    if not name or len(name) > 120 or '@' not in email or len(password) < 8 or not division:
        return jsonify(error='Valid name, email, division and password (at least 8 characters) are required'), 400
    db = mongo.db
    division_doc = db.divisions.find_one({'name': division})
    if not division_doc:
        division_doc = {'name': division, 'created_at': now_utc()}
        division_doc['_id'] = db.divisions.insert_one(division_doc).inserted_id
    role = 'admin' if email.lower() == current_app.config['BOOTSTRAP_ADMIN_EMAIL'] and email else 'user'
    user = {'name': name, 'email': email.lower(), 'password_hash': generate_password_hash(password), 'division_id': division_doc['_id'], 'role': role, 'active': True, 'created_at': now_utc()}
    try:
        user['_id'] = db.users.insert_one(user).inserted_id
    except DuplicateKeyError:
        return jsonify(error='An account with this email already exists'), 409
    return jsonify(token=token_for(user), user=user_public(user)), 201


@auth_bp.post('/auth/login')
def login():
    body = request.get_json(silent=True) or {}
    email, password = str(body.get('email', '')).lower().strip(), str(body.get('password', ''))
    user = mongo.db.users.find_one({'email': email, 'active': True})
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify(error='Invalid email or password'), 401
    return jsonify(token=token_for(user), user=user_public(user)), 200
