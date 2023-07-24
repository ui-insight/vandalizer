
import os
basedir  = os.path.abspath(os.path.dirname(__file__))

class Config(object):
	"""
	Configuration base, for all environments.
	"""
	DEBUG = False
	TESTING = False
	BOOTSTRAP_FONTAWESOME = True
	SECRET_KEY = "MINHACHAVESECRETA"
	SECURITY_PASSWORD_SALT = "MINHACHAVESECRETA"
	CSRF_ENABLED = True
	UPLOAD_FOLDER = "uploads"

	# Pagination
	PER_PAGE = 25


class ProductionConfig(Config):
	DEBUG = False

class DevelopmentConfig(Config):
	DEBUG = True

class TestingConfig(Config):
	TESTING = True
