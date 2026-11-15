from flask import Blueprint, current_app, g, jsonify, request, send_file
from bson import ObjectId
from ..db import mongo, fs
from ..models import can_access, document_public, now_utc, safe_object_id
from ..ocr import extract_text, validate_upload
from ..utils import require_auth
import io, json

documents_bp = Blueprint('documents', __name__)


def accessible_query(user):
    return {'$or': [{'division_id': user['division_id']}, {'authorized_user_ids': user['_id']}]}


@documents_bp.post('/documents/upload')
@require_auth
def upload():
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify(error='A file is required'), 400
    valid, message = validate_upload(uploaded.filename, uploaded.mimetype)
    if not valid:
        return jsonify(error=message), 415
    try:
        metadata = json.loads(request.form.get('metadata', '{}'))
        if not isinstance(metadata, dict) or any(not isinstance(k, str) or len(k) > 100 for k in metadata):
            raise ValueError()
    except (ValueError, json.JSONDecodeError):
        return jsonify(error='metadata must be a JSON object with string keys'), 400
    data = uploaded.read()
    if not data:
        return jsonify(error='Uploaded file is empty'), 400
    title = request.form.get('title', '').strip() or uploaded.filename.rsplit('.', 1)[0][:200]
    try:
        grid_id = fs.upload_from_stream(uploaded.filename, io.BytesIO(data), metadata={'owner_id': str(g.user['_id']), 'division_id': str(g.user['division_id'])})
    except Exception:
        current_app.logger.exception('GridFS upload failed')
        return jsonify(error='File storage is unavailable'), 503
    record = {'title': title[:200], 'filename': uploaded.filename, 'content_type': uploaded.mimetype, 'size': len(data), 'gridfs_id': grid_id, 'division_id': g.user['division_id'], 'owner_id': g.user['_id'], 'metadata': metadata, 'authorized_user_ids': [], 'ocr_status': 'pending', 'extracted_text': '', 'created_at': now_utc()}
    record['_id'] = mongo.db.documents.insert_one(record).inserted_id
    try:
        text = extract_text(data, uploaded.filename, uploaded.mimetype)
        mongo.db.documents.update_one({'_id': record['_id']}, {'$set': {'extracted_text': text, 'ocr_status': 'completed', 'ocr_completed_at': now_utc()}})
        record['ocr_status'] = 'completed'
    except Exception as exc:
        current_app.logger.warning('OCR failed for %s: %s', record['_id'], exc)
        mongo.db.documents.update_one({'_id': record['_id']}, {'$set': {'ocr_status': 'failed', 'ocr_error': str(exc)[:300], 'ocr_completed_at': now_utc()}})
        record.update(ocr_status='failed', ocr_error=str(exc)[:300])
    return jsonify(document=document_public(record)), 201


@documents_bp.get('/documents')
@require_auth
def list_documents():
    query = accessible_query(g.user)
    reserved = {'title', 'q', 'page', 'limit'}
    for key, value in request.args.items():
        if key not in reserved:
            query[f'metadata.{key}'] = value
    if request.args.get('title'):
        query['title'] = {'$regex': request.args['title'], '$options': 'i'}
    limit = min(max(int(request.args.get('limit', 100)), 1), 200)
    docs = mongo.db.documents.find(query).sort('created_at', -1).limit(limit)
    return jsonify(documents=[document_public(d) for d in docs])


@documents_bp.get('/documents/<doc_id>')
@require_auth
def details(doc_id):
    oid = safe_object_id(doc_id)
    doc = mongo.db.documents.find_one({'_id': oid}) if oid else None
    if not doc:
        return jsonify(error='Document not found'), 404
    if not can_access(g.user, doc):
        return jsonify(error='Access denied', request_access_available=True), 403
    return jsonify(document=document_public(doc))


@documents_bp.get('/documents/<doc_id>/download')
@require_auth
def download(doc_id):
    oid = safe_object_id(doc_id)
    doc = mongo.db.documents.find_one({'_id': oid}) if oid else None
    if not doc:
        return jsonify(error='Document not found'), 404
    if not can_access(g.user, doc):
        return jsonify(error='Access denied; an approved request is required'), 403
    try:
        stream = fs.open_download_stream(doc['gridfs_id'])
        payload = stream.read()
    except Exception:
        return jsonify(error='Stored file is unavailable'), 404
    return send_file(io.BytesIO(payload), mimetype=doc['content_type'], as_attachment=True, download_name=doc['filename'])
