"""
Configuration module tests — verifies config classes, secret key generation,
and environment-based config selection.
"""
import os
from unittest.mock import patch


class TestConfigByName:
    """Verify config_by_name mapping resolves to the correct classes."""

    def test_all_environments_present(self):
        from config import config_by_name
        assert 'development' in config_by_name
        assert 'staging' in config_by_name
        assert 'production' in config_by_name
        assert 'testing' in config_by_name

    def test_development_config_class(self):
        from config import config_by_name, DevelopmentConfig
        assert config_by_name['development'] is DevelopmentConfig

    def test_testing_config_class(self):
        from config import config_by_name, TestingConfig
        assert config_by_name['testing'] is TestingConfig

    def test_production_config_class(self):
        from config import config_by_name, ProductionConfig
        assert config_by_name['production'] is ProductionConfig

    def test_staging_config_class(self):
        from config import config_by_name, StagingConfig
        assert config_by_name['staging'] is StagingConfig


class TestGetConfig:
    """Verify get_config() returns the right class based on FLASK_ENV."""

    def test_defaults_to_development(self):
        from config import DevelopmentConfig, get_config
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('FLASK_ENV', None)
            cfg = get_config()
            assert cfg is DevelopmentConfig

    def test_respects_flask_env_testing(self):
        from config import TestingConfig, get_config
        with patch.dict(os.environ, {'FLASK_ENV': 'testing'}):
            assert get_config() is TestingConfig

    def test_unknown_env_falls_back_to_development(self):
        from config import DevelopmentConfig, get_config
        with patch.dict(os.environ, {'FLASK_ENV': 'nonexistent'}):
            assert get_config() is DevelopmentConfig


class TestTestingConfig:
    """TestingConfig specifics."""

    def test_testing_flag(self):
        from config import TestingConfig
        assert TestingConfig.TESTING is True

    def test_csrf_disabled(self):
        from config import TestingConfig
        assert TestingConfig.WTF_CSRF_ENABLED is False

    def test_rate_limiter_disabled(self):
        from config import TestingConfig
        assert TestingConfig.RATELIMIT_ENABLED is False

    def test_secret_key_is_hardcoded(self):
        from config import TestingConfig
        assert TestingConfig.SECRET_KEY == 'test-secret-key-not-for-production'


class TestProductionConfig:
    """ProductionConfig specifics."""

    def test_debug_disabled(self):
        from config import ProductionConfig
        assert ProductionConfig.DEBUG is False

    def test_secure_cookies(self):
        from config import ProductionConfig
        assert ProductionConfig.SESSION_COOKIE_SECURE is True


class TestBaseConfig:
    """Base Config shared properties."""

    def test_session_lifetime_is_8_hours(self):
        from datetime import timedelta
        from config import Config
        assert Config.PERMANENT_SESSION_LIFETIME == timedelta(hours=8)

    def test_session_cookie_httponly(self):
        from config import Config
        assert Config.SESSION_COOKIE_HTTPONLY is True

    def test_session_cookie_samesite(self):
        from config import Config
        assert Config.SESSION_COOKIE_SAMESITE == 'Lax'


class TestSecretKeyGeneration:
    """_generate_secret_key behaviour."""

    def test_env_var_takes_precedence(self):
        from config import _generate_secret_key
        with patch.dict(os.environ, {'SECRET_KEY': 'my-env-secret'}):
            assert _generate_secret_key() == 'my-env-secret'

    def test_returns_nonempty_string(self):
        from config import _generate_secret_key
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SECRET_KEY', None)
            key = _generate_secret_key()
            assert isinstance(key, str)
            assert len(key) > 0
