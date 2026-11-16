
from flask import Blueprint, g, jsonify, request

from ..db import mongo
from ..models import now_utc, safe_object_id
from ..utils import require_auth


access_bp = Blueprint('access', __name__)


@access_bp.post('/access/request')
@require_auth
def request_access():
    body = request.get_json(silent=True) or {}

    doc_id = safe_object_id(str(body.get('doc_id', '')))
    doc = mongo.db.documents.find_one({'_id': doc_id}) if doc_id else None

    if not doc:
        return jsonify(error='Document not found'), 404

    if (
        doc['division_id'] == g.user['division_id']
        or g.user['_id'] in doc.get('authorized_user_ids', [])
    ):
        return jsonify(error='You already have access'), 409

    existing = mongo.db.access_requests.find_one({
        'doc_id': doc['_id'],
        'requester_id': g.user['_id'],
        'status': 'pending',
    })

    if existing:
        return jsonify(
            request_id=str(existing['_id']),
            status='pending',
        ), 200

    req = {
        'doc_id': doc['_id'],
        'requester_id': g.user['_id'],
        'division_id': doc['division_id'],
        'status': 'pending',
        'created_at': now_utc(),
    }

    req['_id'] = mongo.db.access_requests.insert_one(req).inserted_id

    return jsonify(
        request_id=str(req['_id']),
        status=req['status'],
    ), 201


@access_bp.get('/access/requests')
@require_auth
def requests_list():
    outgoing = request.args.get('outgoing', '').lower() == 'true'

    selector = (
        {'requester_id': g.user['_id']}
        if outgoing
        else {'division_id': g.user['division_id']}
    )

    records = list(
        mongo.db.access_requests.find(selector)
        .sort('created_at', -1)
        .limit(200)
    )

    results = []

    for item in records:
        doc = mongo.db.documents.find_one(
            {'_id': item['doc_id']},
            {'title': 1, 'filename': 1},
        )

        requester = mongo.db.users.find_one(
            {'_id': item['requester_id']},
            {'name': 1, 'email': 1, 'division_id': 1},
        )

        requester_division = (
            mongo.db.divisions.find_one(
                {'_id': requester['division_id']}
            )
            if requester
            else None
        )

        results.append({
            'id': str(item['_id']),
            'doc_id': str(item['doc_id']),
            'document_title': (
                doc.get('title') if doc else '[removed]'
            ),
            'requester': {
                'name': requester.get('name'),
                'email': requester.get('email'),
                'division': (
                    requester_division.get('name')
                    if requester_division
                    else None
                ),
            } if requester else None,
            'status': item['status'],
            'created_at': item['created_at'].isoformat(),
        })

    return jsonify(requests=results)


@access_bp.post('/access/approve')
@require_auth
def decide_access():
    body = request.get_json(silent=True) or {}

    rid = safe_object_id(str(body.get('request_id', '')))
    decision = str(body.get('decision', '')).lower()

    if decision not in ('approve', 'reject'):
        return jsonify(
            error='decision must be approve or reject'
        ), 400

    req = (
        mongo.db.access_requests.find_one({'_id': rid})
        if rid
        else None
    )

    if not req:
        return jsonify(error='Access request not found'), 404

    # Only members of the document-owning division can decide.
    if req['division_id'] != g.user['division_id']:
        return jsonify(
            error='Only members of the document division can decide'
        ), 403

    if req['status'] != 'pending':
        return jsonify(
            error='Request has already been decided'
        ), 409

    status = 'approved' if decision == 'approve' else 'rejected'

    # Verify that the document still exists in the owning division.
    doc = mongo.db.documents.find_one({
        '_id': req['doc_id'],
        'division_id': req['division_id'],
    })

    if not doc:
        return jsonify(error='Document not found'), 404

    # Change status only if the request is still pending.
    result = mongo.db.access_requests.update_one(
        {
            '_id': req['_id'],
            'status': 'pending',
        },
        {
            '$set': {
                'status': status,
                'decided_by': g.user['_id'],
                'decided_at': now_utc(),
            }
        }
    )

    # Prevent concurrent decisions from processing the same request.
    if result.modified_count != 1:
        return jsonify(
            error='Request has already been decided'
        ), 409

    # Grant document access only after successful approval.
    if status == 'approved':
        mongo.db.documents.update_one(
            {'_id': req['doc_id']},
            {
                '$addToSet': {
                    'authorized_user_ids': req['requester_id']
                }
            }
        )

    return jsonify(
        request_id=str(req['_id']),
        status=status,
    ), 200
