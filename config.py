"""
Seguimiento Web Configuration
Multi-environment: development / staging / production
"""
import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _generate_secret_key():
    """Generate a persistent secret key."""
    key_file = os.path.join(BASE_DIR, '.flask_secret_key')
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    try:
        with open(key_file, 'w') as f:
            f.write(key)
    except Exception:
        pass
    return key


class Config:
    """Base configuration shared by all environments."""
    SECRET_KEY = _generate_secret_key()

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    WTF_CSRF_TIME_LIMIT = None

    # Defaults
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = False


class DevelopmentConfig(Config):
    """Local development server."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class StagingConfig(Config):
    """Pre-production validation."""
    DEBUG = False
    SESSION_COOKIE_SECURE = False  # Set True when behind HTTPS


class ProductionConfig(Config):
    """Production deployment."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Requires HTTPS

    @classmethod
    def init_app(cls, app):
        """Production-specific app initialization."""
        import logging
        from logging.handlers import RotatingFileHandler

        log_file = os.path.join(BASE_DIR, 'logs', 'production.log')
        handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        ))
        app.logger.addHandler(handler)


class TestingConfig(Config):
    """Pytest configuration — no external dependencies required."""
    TESTING = True
    DEBUG = True
    SECRET_KEY = 'test-secret-key-not-for-production'
    WTF_CSRF_ENABLED = False
    LOGIN_DISABLED = False
    SERVER_NAME = 'localhost.test'

    # Disable rate limiter in tests
    RATELIMIT_ENABLED = False


# Map FLASK_ENV string → config class
config_by_name = {
    'development': DevelopmentConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config():
    """Return the config class for the current FLASK_ENV."""
    env = os.environ.get('FLASK_ENV', 'development')
    return config_by_name.get(env, DevelopmentConfig)
