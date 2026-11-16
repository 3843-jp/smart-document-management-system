
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from bson import ObjectId
from flask import Flask

from app.db import mongo
from app.routes.access import access_bp


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = documents or []

    def find_one(self, query, projection=None):
        return next(
            (
                doc for doc in self.documents
                if all(doc.get(key) == value for key, value in query.items())
            ),
            None,
        )

    def insert_one(self, document):
        document['_id'] = ObjectId()
        self.documents.append(document)
        return SimpleNamespace(inserted_id=document['_id'])

    def update_one(self, query, update):
        doc = self.find_one(query)

        if not doc:
            return SimpleNamespace(modified_count=0)

        for key, value in update.get('$set', {}).items():
            doc[key] = value

        for key, value in update.get('$addToSet', {}).items():
            if value not in doc.setdefault(key, []):
                doc[key].append(value)

        return SimpleNamespace(modified_count=1)


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        self.documents = sorted(
            self.documents,
            key=lambda doc: doc.get(field),
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeAccessRequests(FakeCollection):
    def find(self, query):
        records = [
            doc for doc in self.documents
            if all(doc.get(key) == value for key, value in query.items())
        ]
        return FakeCursor(records)


@pytest.fixture
def access_client():
    requester_id = ObjectId()
    owner_id = ObjectId()
    outsider_id = ObjectId()

    division_a = ObjectId()
    division_b = ObjectId()
    division_c = ObjectId()

    document_id = ObjectId()

    users = FakeCollection([
        {
            '_id': requester_id,
            'name': 'Requester',
            'email': 'requester@example.com',
            'division_id': division_b,
            'active': True,
        },
        {
            '_id': owner_id,
            'name': 'Owner',
            'email': 'owner@example.com',
            'division_id': division_a,
            'active': True,
        },
        {
            '_id': outsider_id,
            'name': 'Outsider',
            'email': 'outsider@example.com',
            'division_id': division_c,
            'active': True,
        },
    ])

    documents = FakeCollection([
        {
            '_id': document_id,
            'title': 'Confidential Report',
            'filename': 'report.pdf',
            'division_id': division_a,
            'authorized_user_ids': [],
        }
    ])

    requests = FakeAccessRequests()

    divisions = FakeCollection([
        {'_id': division_a, 'name': 'Division A'},
        {'_id': division_b, 'name': 'Division B'},
        {'_id': division_c, 'name': 'Division C'},
    ])

    db = SimpleNamespace(
        users=users,
        documents=documents,
        access_requests=requests,
        divisions=divisions,
    )

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY='test-secret-key-for-jwt-at-least-32-bytes',
        TOKEN_TTL_HOURS=1,
        TESTING=True,
    )

    original_db = mongo.db

    def make_token(user_id):
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                'sub': str(user_id),
                'iat': now,
                'exp': now + timedelta(hours=1),
            },
            app.config['SECRET_KEY'],
            algorithm='HS256',
        )

    try:
        mongo.db = db
        app.extensions['pymongo'] = SimpleNamespace(db=db)
        app.register_blueprint(access_bp, url_prefix='/api')

        client = app.test_client()

        def authenticate(user_id):
            client.environ_base['HTTP_AUTHORIZATION'] = (
                f'Bearer {make_token(user_id)}'
            )

        yield SimpleNamespace(
            client=client,
            authenticate=authenticate,
            requester_id=requester_id,
            owner_id=owner_id,
            outsider_id=outsider_id,
            division_a=division_a,
            division_b=division_b,
            document_id=document_id,
            documents=documents,
            requests=requests,
        )

    finally:
        mongo.db = original_db


def test_user_can_request_cross_division_access(access_client):
    access_client.authenticate(access_client.requester_id)

    response = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    assert response.status_code == 201
    assert response.get_json()['status'] == 'pending'


def test_duplicate_pending_request_is_not_created(access_client):
    access_client.authenticate(access_client.requester_id)

    first = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    second = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert len(access_client.requests.documents) == 1


def test_outsider_cannot_approve_request(access_client):
    access_client.authenticate(access_client.requester_id)

    request_response = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    request_id = request_response.get_json()['request_id']

    access_client.authenticate(access_client.outsider_id)

    response = access_client.client.post(
        '/api/access/approve',
        json={
            'request_id': request_id,
            'decision': 'approve',
        },
    )

    assert response.status_code == 403
    assert access_client.documents.documents[0]['authorized_user_ids'] == []


def test_owner_division_member_can_approve_request(access_client):
    access_client.authenticate(access_client.requester_id)

    request_response = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    request_id = request_response.get_json()['request_id']

    access_client.authenticate(access_client.owner_id)

    response = access_client.client.post(
        '/api/access/approve',
        json={
            'request_id': request_id,
            'decision': 'approve',
        },
    )

    assert response.status_code == 200
    assert response.get_json()['status'] == 'approved'

    assert (
        access_client.requester_id
        in access_client.documents.documents[0]['authorized_user_ids']
    )


def test_rejected_request_does_not_grant_access(access_client):
    access_client.authenticate(access_client.requester_id)

    request_response = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    request_id = request_response.get_json()['request_id']

    access_client.authenticate(access_client.owner_id)

    response = access_client.client.post(
        '/api/access/approve',
        json={
            'request_id': request_id,
            'decision': 'reject',
        },
    )

    assert response.status_code == 200
    assert response.get_json()['status'] == 'rejected'
    assert access_client.documents.documents[0]['authorized_user_ids'] == []


def test_already_decided_request_cannot_be_approved_again(access_client):
    access_client.authenticate(access_client.requester_id)

    request_response = access_client.client.post(
        '/api/access/request',
        json={'doc_id': str(access_client.document_id)},
    )

    request_id = request_response.get_json()['request_id']

    access_client.authenticate(access_client.owner_id)

    first_response = access_client.client.post(
        '/api/access/approve',
        json={
            'request_id': request_id,
            'decision': 'approve',
        },
    )

    second_response = access_client.client.post(
        '/api/access/approve',
        json={
            'request_id': request_id,
            'decision': 'reject',
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
