import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuration base, for all environments."""

    DEBUG = False
    TESTING = False
    BOOTSTRAP_FONTAWESOME = True
    SECRET_KEY = "***REMOVED***"
    SECURITY_PASSWORD_SALT = "***REMOVED***"
    CSRF_ENABLED = True
    UPLOAD_FOLDER = "uploads"

    MAIL_SERVER = "mail.nkn.uidaho.edu"
    MAIL_PORT = 25
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_DEFAULT_SENDER = "bugs@insight.uidaho.edu"
    MAIL_SUPPRESS_SEND = False

    EMAIL_RECIPIENTS = ["jbrunsfeld@uidaho.edu"]

    CLIENT_ID = "d135cfa9-546c-48f6-a5be-a0a97955bc61"  # os.getenv('CLIENT_ID')
    CLIENT_SECRET = (
        "iRr8Q~wUZCIi0AkTmO1uTlsvWgYMtvms2yzdvaEN"  # os.getenv('CLIENT_SECRET')
    )
    TENANT_NAME = "7ebc6b63-5792-4a19-b20b-04b826048853"  # os.getenv('TENANT_NAME')

    # Pagination
    PER_PAGE = 25


class ProductionConfig(Config):
    """Production configuration."""

    MONGO_DB = "osp"
    DEBUG = False


class DevelopmentConfig(Config):
    """Development configuration."""

    MONGO_DB = "osp"
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""

    MONGO_DB = "osp-staging"
    TESTING = True
