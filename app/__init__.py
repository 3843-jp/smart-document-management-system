from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge
from .config import Config
from .db import init_db
from .routes.auth import auth_bp
from .routes.documents import documents_bp
from .routes.access import access_bp
from .routes.search import search_bp
from .routes.metadata import metadata_bp


def create_app(config_override=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)
    init_db(app)
    for blueprint in (auth_bp, documents_bp, access_bp, search_bp, metadata_bp):
        app.register_blueprint(blueprint, url_prefix='/api')

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify(error='Upload exceeds configured size limit'), 413

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error='Not found'), 404

    return app
