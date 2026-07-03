"""
Authentication routes for Open-OMS
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import current_app, limiter
from models import User

auth_bp = Blueprint("auth", __name__)


def _is_safe_url(target):
    """Validate that redirect target is a safe relative URL."""
    from urllib.parse import urljoin, urlparse

    from flask import request as _req

    ref_url = urlparse(_req.host_url)
    test_url = urlparse(urljoin(_req.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    """User login page"""
    if current_user.is_authenticated:
        if current_user.username.lower() in ["mostrador", "monitor"]:
            return redirect(url_for("orders.monitor"))  # pragma: no cover
        return redirect(url_for("orders.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        if not username or not password:
            flash("Por favor ingrese usuario y contraseña", "error")
            return render_template("auth/login.html")

        user_manager = current_app.user_manager
        if user_manager.authenticate(username, password):
            user_data = user_manager.get_current_user()
            if user_data is None:
                flash("Error interno: usuario no encontrado", "error")
                return render_template("auth/login.html")
            user = User(user_data)

            if not user.is_active:
                flash("Su cuenta ha sido desactivada.", "error")
                return render_template("auth/login.html")

            login_user(user, remember=remember)

            if user.must_change_password:
                flash("Debe cambiar su contraseña antes de continuar", "warning")
                return redirect(url_for("auth.change_password"))

            flash(f"Bienvenido, {user.full_name}", "success")

            next_page = request.args.get("next")
            if next_page and not _is_safe_url(next_page):
                next_page = None
            if not next_page and user.username.lower() in ["mostrador", "monitor"]:
                return redirect(url_for("orders.monitor"))
            return redirect(next_page or url_for("orders.index"))
        else:
            flash("Usuario o contraseña incorrectos", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """User logout"""
    logout_user()
    flash("Sesión cerrada exitosamente", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change password page"""
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([current_password, new_password, confirm_password]):
            flash("Todos los campos son requeridos", "error")
            return render_template("auth/change_password.html")

        if new_password != confirm_password:
            flash("Las contraseñas nuevas no coinciden", "error")
            return render_template("auth/change_password.html")

        if len(new_password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres", "error")
            return render_template("auth/change_password.html")

        user_manager = current_app.user_manager
        if not user_manager.authenticate(current_user.username, current_password):
            flash("Contraseña actual incorrecta", "error")
            return render_template("auth/change_password.html")

        req_user = {"username": current_user.username, "role": current_user.role}
        success, message = user_manager.update_user(
            current_user.username, requesting_user=req_user, password=new_password
        )
        if success:
            flash("Contraseña cambiada exitosamente", "success")
            return redirect(url_for("orders.index"))
        else:
            flash(f"Error: {message}", "error")

    return render_template("auth/change_password.html")

