from flask import Blueprint, g, jsonify, request
from ..db import mongo
from ..models import can_access, document_public
from ..utils import require_auth

search_bp = Blueprint('search', __name__)


@search_bp.get('/search')
@require_auth
def search():
    term = request.args.get('q', '').strip()
    if not term:
        return jsonify(results=[])
    escaped = __import__('re').escape(term)
    matcher = {'$regex': escaped, '$options': 'i'}
    query = {'$and': [
        {'$or': [{'division_id': g.user['division_id']}, {'authorized_user_ids': g.user['_id']}]},
        {'$or': [{'title': matcher}, {'extracted_text': matcher}, {'metadata': {'$elemMatch': {'$regex': escaped, '$options': 'i'}}}]}
    ]}
    # Metadata is a dynamic object, so inspect its arbitrary values safely in the bounded candidate set.
    candidates = mongo.db.documents.find({'$or': [{'division_id': g.user['division_id']}, {'authorized_user_ids': g.user['_id']}]}, {'extracted_text': 0}).sort('created_at', -1).limit(1000)
    # Query title and OCR in MongoDB; metadata values are dynamically evaluated without leaking unauthorized docs.
    results = []
    for doc in candidates:
        text_match = bool(__import__('re').search(escaped, doc.get('title', ''), __import__('re').I) or __import__('re').search(escaped, doc.get('extracted_text', ''), __import__('re').I))
        metadata_match = any(__import__('re').search(escaped, str(value), __import__('re').I) for value in (doc.get('metadata') or {}).values())
        if text_match or metadata_match:
            results.append(document_public(doc))
            if len(results) >= 100:
                break
    return jsonify(results=results)
