#!/usr/bin/env python3

from app import create_app

flask_app = create_app()
celery_app = flask_app.extensions["celery"]

# Tasks are auto-discovered by Celery when modules containing @celery_app.task decorators
# are imported. They will be imported when Flask app starts (through blueprints).
# No need to import them here to avoid circular import issues.
