import re

from flask import Blueprint, g, jsonify, request

from ..db import mongo
from ..models import document_public
from ..utils import require_auth

search_bp = Blueprint('search', __name__)


@search_bp.get('/search')
@require_auth
def search():
    term = request.args.get('q', '').strip()
    if not term:
        return jsonify(results=[])

    escaped = re.escape(term)
    access_filter = {
        '$or': [
            {'division_id': g.user['division_id']},
            {'authorized_user_ids': g.user['_id']},
        ]
    }
    # Metadata is dynamic, so inspect its values in the bounded, access-filtered candidate set.
    candidates = mongo.db.documents.find(access_filter).sort('created_at', -1).limit(1000)

    results = []
    for doc in candidates:
        text_match = bool(
            re.search(escaped, str(doc.get('title') or ''), re.I)
            or re.search(escaped, str(doc.get('extracted_text') or ''), re.I)
        )
        metadata_match = any(
            re.search(escaped, str(value), re.I)
            for value in (doc.get('metadata') or {}).values()
        )
        if text_match or metadata_match:
            results.append(document_public(doc))
            if len(results) >= 100:
                break

    return jsonify(results=results)
