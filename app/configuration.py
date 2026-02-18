import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuration base, for all environments."""

    DEBUG = False
    TESTING = False
    BOOTSTRAP_FONTAWESOME = True
    # Default to CDN assets unless explicitly enabled via env var.
    BOOTSTRAP_SERVE_LOCAL = (
        os.getenv("BOOTSTRAP_SERVE_LOCAL", "false").strip().lower() == "true"
    )
    SECRET_KEY = "***REMOVED***"
    SECURITY_PASSWORD_SALT = "***REMOVED***"
    CSRF_ENABLED = True
    UPLOAD_FOLDER = "uploads"

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
    MAIL_SERVER = "mail.nkn.uidaho.edu"
    MAIL_PORT = 25
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_DEFAULT_SENDER = "vandalizer@insight.uidaho.edu"
    MAIL_SUPPRESS_SEND = False


class DevelopmentConfig(Config):
    """Development configuration."""

    MONGO_DB = "osp"
    DEBUG = True
    MAIL_SERVER = ("localhost",)
    MAIL_PORT = (1025,)
    MAIL_USE_TLS = (False,)
    MAIL_USE_SSL = (False,)
    MAIL_USERNAME = (None,)
    MAIL_PASSWORD = (None,)


class TestingConfig(Config):
    """Testing configuration."""

    MONGO_DB = "osp-staging"
    TESTING = True
    MAIL_SERVER = "mail.nkn.uidaho.edu"
    MAIL_PORT = 25
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_DEFAULT_SENDER = "vandalizer@insight.uidaho.edu"
    MAIL_SUPPRESS_SEND = False
