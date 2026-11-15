from flask import Blueprint, g, jsonify, request
from pymongo.errors import DuplicateKeyError
from ..db import mongo
from ..models import now_utc, safe_object_id
from ..utils import require_admin, require_auth

metadata_bp = Blueprint('metadata', __name__)


@metadata_bp.get('/divisions')
def divisions():
    return jsonify(divisions=[{'id': str(d['_id']), 'name': d['name']} for d in mongo.db.divisions.find({}, {'name': 1}).sort('name', 1)])


@metadata_bp.get('/metadata/fields')
@require_auth
def fields():
    return jsonify(fields=[{'id': str(x['_id']), 'name': x['name'], 'label': x.get('label', x['name']), 'type': x.get('type', 'text'), 'required': x.get('required', False), 'filterable': x.get('filterable', True), 'options': x.get('options', [])} for x in mongo.db.metadata_fields.find({}).sort('name', 1)])


@metadata_bp.post('/metadata/fields')
@require_auth
@require_admin
def create_field():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name', '')).strip()
    if not name or len(name) > 100 or name.startswith('$') or '.' in name:
        return jsonify(error='Field name must be 1-100 characters and cannot contain dots'), 400
    field = {'name': name, 'label': str(body.get('label', name))[:100], 'type': body.get('type', 'text'), 'required': bool(body.get('required', False)), 'filterable': bool(body.get('filterable', True)), 'options': body.get('options', []) if isinstance(body.get('options', []), list) else [], 'created_at': now_utc(), 'updated_at': now_utc()}
    try:
        field['_id'] = mongo.db.metadata_fields.insert_one(field).inserted_id
    except DuplicateKeyError:
        return jsonify(error='Metadata field already exists'), 409
    return jsonify(field={**{k: v for k, v in field.items() if k != '_id'}, 'id': str(field['_id'])}), 201


@metadata_bp.put('/metadata/fields/<field_id>')
@require_auth
@require_admin
def edit_field(field_id):
    oid = safe_object_id(field_id)
    body = request.get_json(silent=True) or {}
    update = {}
    for key in ('label', 'type', 'required', 'filterable', 'options'):
        if key in body:
            update[key] = body[key]
    if 'name' in body:
        name = str(body['name']).strip()
        if not name or len(name) > 100 or '.' in name or name.startswith('$'):
            return jsonify(error='Invalid field name'), 400
        update['name'] = name
    if not update:
        return jsonify(error='No editable properties supplied'), 400
    update['updated_at'] = now_utc()
    result = mongo.db.metadata_fields.update_one({'_id': oid}, {'$set': update}) if oid else None
    if not result or result.matched_count == 0:
        return jsonify(error='Metadata field not found'), 404
    return jsonify(status='updated')
