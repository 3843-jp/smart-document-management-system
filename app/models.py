from datetime import datetime, timezone
from bson import ObjectId
from .db import mongo


def now_utc():
    return datetime.now(timezone.utc)


def user_public(user):
    division = mongo.db.divisions.find_one({'_id': user['division_id']})
    return {'id': str(user['_id']), 'name': user['name'], 'email': user['email'], 'role': user['role'], 'division': division['name'] if division else None, 'division_id': str(user['division_id'])}


def document_public(doc):
    division = mongo.db.divisions.find_one({'_id': doc['division_id']})
    return {'id': str(doc['_id']), 'title': doc.get('title'), 'filename': doc.get('filename'), 'content_type': doc.get('content_type'), 'size': doc.get('size'), 'division': division['name'] if division else None, 'division_id': str(doc['division_id']), 'metadata': doc.get('metadata', {}), 'ocr_status': doc.get('ocr_status', 'pending'), 'ocr_error': doc.get('ocr_error'), 'created_at': doc.get('created_at').isoformat() if doc.get('created_at') else None}


def can_access(user, doc):
    return user['division_id'] == doc['division_id'] or user['_id'] in doc.get('authorized_user_ids', [])


def safe_object_id(value):
    return ObjectId(value) if ObjectId.is_valid(value) else None
