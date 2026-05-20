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


class TestStagingConfig:
    """StagingConfig specifics."""

    def test_debug_disabled(self):
        from config import StagingConfig
        assert StagingConfig.DEBUG is False

    def test_session_cookie_not_secure(self):
        from config import StagingConfig
        assert StagingConfig.SESSION_COOKIE_SECURE is False


class TestProductionInitApp:
    def test_init_app_adds_handler(self, app):
        from unittest.mock import MagicMock
        from config import ProductionConfig
        with patch("logging.handlers.RotatingFileHandler") as mock_handler_cls:
            mock_handler = MagicMock()
            mock_handler.level = 10
            mock_handler_cls.return_value = mock_handler

            ProductionConfig.init_app(app)

            # verify app.logger has our mock_handler
            assert mock_handler in app.logger.handlers
            mock_handler.setLevel.assert_called_once()
            mock_handler.setFormatter.assert_called_once()
            
            # cleanup
            app.logger.removeHandler(mock_handler)


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

    def test_reads_from_key_file(self):
        import tempfile
        from config import _generate_secret_key

        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False)
        tmp.write('file-secret-key')
        tmp.close()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SECRET_KEY', None)
            with patch("config.os.path.join", return_value=tmp.name):
                key = _generate_secret_key()
        assert key == 'file-secret-key'
        os.unlink(tmp.name)

    def test_generates_and_writes_key(self):
        import tempfile
        from config import _generate_secret_key

        tmp_dir = tempfile.mkdtemp()
        key_path = os.path.join(tmp_dir, '.flask_secret_key')

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SECRET_KEY', None)
            with patch("config.os.path.join", return_value=key_path):
                key = _generate_secret_key()

        assert len(key) == 64  # hex of 32 bytes
        assert os.path.exists(key_path)
        os.unlink(key_path)
        os.rmdir(tmp_dir)

    def test_write_failure_still_returns_key(self):
        from config import _generate_secret_key

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SECRET_KEY', None)
            with patch("config.os.path.join", return_value="/nonexistent/dir/.flask_secret_key"):
                with patch("config.os.path.exists", return_value=False):
                    key = _generate_secret_key()
        assert isinstance(key, str)
        assert len(key) > 0
