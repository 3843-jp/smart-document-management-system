from flask_pymongo import PyMongo
from gridfs import GridFSBucket

mongo = PyMongo()
fs = None


def init_db(app):
    global fs
    mongo.init_app(app)
    with app.app_context():
        db = mongo.db
        db.users.create_index('email', unique=True)
        db.divisions.create_index('name', unique=True)
        db.documents.create_index([('division_id', 1), ('created_at', -1)])
        db.documents.create_index([('title', 'text'), ('extracted_text', 'text')])
        db.access_requests.create_index([('division_id', 1), ('status', 1)])
        db.metadata_fields.create_index('name', unique=True)
        fs = GridFSBucket(db, bucket_name='documents')
