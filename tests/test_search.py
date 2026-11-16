
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from bson import ObjectId
from flask import Flask

from app.db import mongo
from app.routes.search import search_bp


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


class FakeDocuments:
    def __init__(self, documents):
        self.documents = documents

    def find(self, query, projection=None):
        clauses = query['$or']

        matching = [
            doc for doc in self.documents
            if any(
                (
                    'division_id' in clause
                    and doc.get('division_id') == clause['division_id']
                )
                or (
                    'authorized_user_ids' in clause
                    and clause['authorized_user_ids']
                    in doc.get('authorized_user_ids', [])
                )
                for clause in clauses
            )
        ]

        return FakeCursor(matching)


@pytest.fixture
def search_client():
    user_id = ObjectId()
    division_id = ObjectId()
    other_division_id = ObjectId()

    user = {
        '_id': user_id,
        'division_id': division_id,
        'active': True,
    }

    documents = []

    db = SimpleNamespace(
        users=SimpleNamespace(
            find_one=lambda query: (
                user
                if query.get('_id') == user_id
                and query.get('active') is True
                else None
            )
        ),
        divisions=SimpleNamespace(
            find_one=lambda query: {'name': 'Division'}
        ),
        documents=FakeDocuments(documents),
    )

    app = Flask(__name__)

    app.config.update(
        SECRET_KEY='test-secret-key-for-jwt-at-least-32-bytes',
        TOKEN_TTL_HOURS=1,
        TESTING=True,
    )

    original_db = mongo.db

    try:
        mongo.db = db
        app.extensions['pymongo'] = SimpleNamespace(db=db)

        app.register_blueprint(search_bp, url_prefix='/api')

        now = datetime.now(timezone.utc)

        token = jwt.encode(
            {
                'sub': str(user_id),
                'iat': now,
                'exp': now + timedelta(hours=1),
            },
            app.config['SECRET_KEY'],
            algorithm='HS256',
        )

        client = app.test_client()
        client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        yield client, db.documents, division_id, other_division_id, user_id

    finally:
        mongo.db = original_db


def make_document(division_id, **fields):
    return {
        '_id': ObjectId(),
        'division_id': division_id,
        'created_at': datetime.now(timezone.utc),
        'title': '',
        'extracted_text': '',
        'metadata': {},
        'authorized_user_ids': [],
        **fields,
    }


def result_titles(response):
    assert response.status_code == 200, response.get_json()

    return [
        document['title']
        for document in response.get_json()['results']
    ]


def test_search_matches_document_title(search_client):
    client, collection, division_id, _, _ = search_client

    collection.documents.append(
        make_document(division_id, title='Quarterly forecast')
    )

    assert result_titles(
        client.get('/api/search?q=forecast')
    ) == ['Quarterly forecast']


def test_search_matches_ocr_extracted_text(search_client):
    client, collection, division_id, _, _ = search_client

    collection.documents.append(
        make_document(
            division_id,
            title='Scanned report',
            extracted_text='Payment received',
        )
    )

    assert result_titles(
        client.get('/api/search?q=payment')
    ) == ['Scanned report']


def test_search_matches_dynamic_metadata_values(search_client):
    client, collection, division_id, _, _ = search_client

    collection.documents.append(
        make_document(
            division_id,
            title='Invoice',
            metadata={'project_code': 'Orchid-42'},
        )
    )

    assert result_titles(
        client.get('/api/search?q=orchid')
    ) == ['Invoice']


def test_search_is_division_isolated_but_allows_approved_cross_division_access(
    search_client,
):
    client, collection, division_id, other_division_id, user_id = search_client

    collection.documents.extend([
        make_document(
            division_id,
            title='Shared policy',
        ),
        make_document(
            other_division_id,
            title='Approved shared policy',
            authorized_user_ids=[user_id],
        ),
        make_document(
            other_division_id,
            title='Private shared policy',
        ),
    ])

    results = result_titles(
        client.get('/api/search?q=shared')
    )

    assert set(results) == {
        'Shared policy',
        'Approved shared policy',
    }

    assert 'Private shared policy' not in results


def test_search_escapes_regex_metacharacters(search_client):
    client, collection, division_id, _, _ = search_client

    collection.documents.extend([
        make_document(
            division_id,
            title='Literal .* document',
        ),
        make_document(
            division_id,
            title='Any matching document',
        ),
    ])

    assert result_titles(
        client.get('/api/search?q=.*')
    ) == ['Literal .* document']
