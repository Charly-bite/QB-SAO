"""
Open-OMS — Order Tracking Application
Independent module for order status monitoring and management.
"""

import io
import logging
import os
import sys
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from flask_limiter import Limiter

    from core.sap_connector import SAPHanaConnector as _SAPHanaConnectorType

# Central logging
os.makedirs(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"), exist_ok=True
)
log_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "logs", "open_oms.log"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

# Add core directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

# Fix Windows console encoding
if sys.platform == "win32" and "pytest" not in sys.modules:  # pragma: no cover
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    except Exception:
        pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from flask import (  # noqa: E402
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import LoginManager  # noqa: E402
from flask_wtf.csrf import CSRFError, CSRFProtect  # noqa: E402

from config import config_by_name, get_config  # noqa: E402
from core.order_status_manager import OrderStatus, OrderStatusManager  # noqa: E402
from core.user_manager import UserManager, UserRole  # noqa: E402
from extensions import limiter as _limiter  # noqa: E402

# Optional SAP connector
try:
    from core.sap_connector import SAPHanaConnector

    SAP_AVAILABLE = True
    print("✅ SAP connector available")
except ImportError:  # pragma: no cover
    SAPHanaConnector = None
    SAP_AVAILABLE = False
    print("⚠️ SAP connector not available (hdbcli missing)")


class OpenOMSApp(Flask):
    """Flask subclass that declares custom app-level attributes for type safety."""

    user_manager: "UserManager"
    order_status_mgr: "OrderStatusManager"
    sap_connector: "Optional[_SAPHanaConnectorType]"
    sap_available: bool
    csrf: "CSRFProtect"
    limiter: "Limiter"  # type: ignore[type-arg]


def create_app(config_name: Optional[str] = None) -> "OpenOMSApp":
    """Application factory.

    Args:
        config_name: One of 'development', 'staging', 'production', 'testing'.
                     Defaults to FLASK_ENV environment variable.
    """
    app = OpenOMSApp(__name__)

    if config_name:
        app.config.from_object(config_by_name[config_name])
    else:
        app.config.from_object(get_config())

    # CSRF protection
    csrf = CSRFProtect(app)
    app.csrf = csrf

    _original_protect = csrf.protect

    def _graceful_protect(*args, **kwargs):
        try:  # pragma: no cover
            _original_protect(*args, **kwargs)  # pragma: no cover
        except CSRFError:  # pragma: no cover
            from flask import session as flask_session

            flask_session.pop("csrf_token", None)
            flash("Su sesión expiró. Por favor intente de nuevo.", "warning")
            response = redirect(url_for("auth.login"))
            from werkzeug.exceptions import HTTPException

            exc = HTTPException(response=response)
            exc.code = 302
            raise exc

    csrf.protect = _graceful_protect

    # Rate limiter
    _limiter.init_app(app)
    app.limiter = _limiter

    # Jinja globals
    app.jinja_env.globals.update(zip=zip)

    # Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # type: ignore[assignment]
    login_manager.login_message = "Por favor inicie sesión para acceder."
    login_manager.login_message_category = "warning"

    # Initialize managers
    app.user_manager = UserManager()
    app.order_status_mgr = OrderStatusManager()

    # SAP Connector (lazy connection)
    app.sap_connector = None
    app.sap_available = SAP_AVAILABLE

    if SAP_AVAILABLE:
        sap_user = os.environ.get("SAP_USER")
        sap_pass = os.environ.get("SAP_PASS")
        if sap_user and sap_pass and SAPHanaConnector is not None:
            try:
                app.sap_connector = SAPHanaConnector(
                    host=os.environ.get("SAP_HOST", "20.0.1.9"),
                    port=int(os.environ.get("SAP_PORT", 30015)),
                    username=sap_user,
                    password=sap_pass,
                    schema=os.environ.get("SAP_SCHEMA", "SBO_QUIMICABOSS"),
                )
                print("✅ SAP Connector initialized (Lazy connection mode)")
            except Exception as e:
                print(f"⚠️ SAP Connector initialization error: {e}")
                app.sap_connector = None

    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        from models import User

        user_data = app.user_manager.get_user(user_id)
        if user_data:
            return User(user_data)
        return None  # pragma: no cover

    # Register blueprints
    from routes.auth import auth_bp
    from routes.orders import orders_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(orders_bp, url_prefix="/orders")

    # Request logger middleware
    from middleware.request_logger import init_request_logger

    init_request_logger(app)

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        if request.path.startswith("/api/") or request.is_json:  # pragma: no cover
            return jsonify(
                {"error": "Internal server error", "message": str(error)}
            ), 500
        return render_template("errors/500.html"), 500

    # Favicon
    @app.route("/favicon.ico")
    def favicon():
        return app.send_static_file("images/logo_vertical.2.png")

    # Context processor
    @app.context_processor
    def utility_processor():
        return {
            "sap_available": SAP_AVAILABLE,
            "UserRole": UserRole,
            "OrderStatus": OrderStatus,
        }

    # Dashboard redirect
    @app.route("/")
    def index():
        return redirect(url_for("orders.index"))

    # Health check
    @app.route("/health")
    def health_check():
        return jsonify(
            {
                "status": "ok",
                "app": "Open-OMS",
                "sap_available": SAP_AVAILABLE,
                "orders_loaded": len(app.order_status_mgr.orders),
            }
        )

    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    print("=" * 60)
    print("📦  Open-OMS — Order Tracking System")
    print("=" * 60)
    print(f"🔌 SAP Available: {SAP_AVAILABLE}")
    print(f"📊 Orders loaded: {len(app.order_status_mgr.orders)}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5003, debug=True)

