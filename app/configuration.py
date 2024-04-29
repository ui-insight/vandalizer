
import os
basedir  = os.path.abspath(os.path.dirname(__file__))

class Config(object):
	"""
	Configuration base, for all environments.
	"""
	DEBUG = False
	TESTING = False
	BOOTSTRAP_FONTAWESOME = True
	SECRET_KEY = "***REMOVED***"
	SECURITY_PASSWORD_SALT = "***REMOVED***"
	CSRF_ENABLED = True
	UPLOAD_FOLDER = "uploads"

	CLIENT_ID = "d135cfa9-546c-48f6-a5be-a0a97955bc61"#os.getenv('CLIENT_ID')
	CLIENT_SECRET = "iRr8Q~wUZCIi0AkTmO1uTlsvWgYMtvms2yzdvaEN"#os.getenv('CLIENT_SECRET')
	TENANT_NAME = "7ebc6b63-5792-4a19-b20b-04b826048853"#os.getenv('TENANT_NAME')

	# Pagination
	PER_PAGE = 25


class ProductionConfig(Config):
	DEBUG = False

class DevelopmentConfig(Config):
	DEBUG = True

class TestingConfig(Config):
	TESTING = True
