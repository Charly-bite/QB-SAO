"""
User management routes for Open-OMS
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
import os
from werkzeug.utils import secure_filename
from flask_login import current_user, login_required

from extensions import current_app
from core.user_manager import UserRole

users_bp = Blueprint("users", __name__, url_prefix="/users")

@users_bp.before_request
@login_required
def require_view_users():  # pragma: no cover
    """Ensure all user management routes are only accessible by admins or viewers."""
    if not current_user.can_view_users():
        flash("Acceso denegado. Se requieren permisos.", "error")
        return redirect(url_for("orders.index"))

@users_bp.route("/")
def index():  # pragma: no cover
    """List all users"""
    user_manager = current_app.user_manager
    users = user_manager.get_all_users()
    
    import datetime
    now = datetime.datetime.now()
    for u in users:
        u['is_online'] = False
        if u.get('last_active_at'):
            try:
                dt = datetime.datetime.fromisoformat(u['last_active_at'])
                if (now - dt).total_seconds() < 900: # 15 minutes
                    u['is_online'] = True
            except:
                pass
                
        u['last_login_fmt'] = '-'
        if u.get('last_login'):
            try:
                dt = datetime.datetime.fromisoformat(u['last_login'])
                u['last_login_fmt'] = dt.strftime("%d/%m/%Y %H:%M")
            except:
                u['last_login_fmt'] = u['last_login']
                
    return render_template("users/list.html", users=users)

def _save_signature_file(username, file_obj, app):  # pragma: no cover
    """Save a signature file and return the relative static path."""
    if not file_obj or file_obj.filename == '':
        return None
    ext = file_obj.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['png', 'jpg', 'jpeg']:
        return None
    
    filename = secure_filename(f"{username}_signature.{ext}")
    save_dir = os.path.join(app.static_folder, 'images', 'signatures')
    os.makedirs(save_dir, exist_ok=True)
    
    file_path = os.path.join(save_dir, filename)
    file_obj.save(file_path)
    return f"images/signatures/{filename}"

@users_bp.route("/create", methods=["GET", "POST"])
def create():  # pragma: no cover
    """Create a new user"""
    if not current_user.is_admin():
        flash("Solo los administradores pueden crear usuarios.", "error")
        return redirect(url_for("users.index"))
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "viewer")
        sap_seller_name = request.form.get("sap_seller_name", "").strip()
        signature_file = request.files.get("signature")

        if not username or not password:
            flash("Usuario y contraseña son requeridos", "error")
            return render_template("users/form.html", user=None, roles=list(UserRole))

        signature_path = _save_signature_file(username, signature_file, current_app) if signature_file else ""

        user_manager = current_app.user_manager
        success, message = user_manager.create_user(
            username=username,
            password=password,
            full_name=full_name,
            email=email,
            role=role,
            requesting_user={"role": "admin"},
            sap_seller_name=sap_seller_name,
            signature_path=signature_path
        )

        if success:
            flash("Usuario creado exitosamente", "success")
            return redirect(url_for("users.index"))
        else:
            flash(f"Error: {message}", "error")

    return render_template("users/form.html", user=None, roles=list(UserRole))

@users_bp.route("/<username>/edit", methods=["GET", "POST"])
def edit(username):  # pragma: no cover
    """Edit an existing user"""
    if not current_user.is_admin():
        flash("Solo los administradores pueden editar usuarios.", "error")
        return redirect(url_for("users.index"))
        
    user_manager = current_app.user_manager
    user = user_manager.get_user(username)

    if not user:
        flash("Usuario no encontrado", "error")
        return redirect(url_for("users.index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", user.get("role"))
        is_active = request.form.get("is_active") == "on"
        sap_seller_name = request.form.get("sap_seller_name", "").strip()
        password = request.form.get("password", "")
        signature_file = request.files.get("signature")

        kwargs = {
            "full_name": full_name,
            "email": email,
            "role": role,
            "is_active": is_active,
            "sap_seller_name": sap_seller_name
        }

        if signature_file and signature_file.filename:
            sig_path = _save_signature_file(username, signature_file, current_app)
            if sig_path:
                kwargs["signature_path"] = sig_path

        if password:
            kwargs["password"] = password

        success, message = user_manager.update_user(
            username=username,
            requesting_user={"role": "admin"},
            **kwargs
        )

        if success:
            flash("Usuario actualizado exitosamente", "success")
            return redirect(url_for("users.index"))
        else:
            flash(f"Error: {message}", "error")

    return render_template("users/form.html", user=user, roles=list(UserRole))

@users_bp.route("/<username>/delete", methods=["POST"])
def delete(username):  # pragma: no cover
    """Delete a user"""
    if not current_user.is_admin():
        flash("Solo los administradores pueden eliminar usuarios.", "error")
        return redirect(url_for("users.index"))
        
    user_manager = current_app.user_manager
    success, message = user_manager.delete_user(
        username=username,
        requesting_user={"role": "admin"}
    )

    if success:
        flash("Usuario eliminado exitosamente", "success")
    else:
        flash(f"Error: {message}", "error")

    return redirect(url_for("users.index"))
