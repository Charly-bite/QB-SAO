"""
Quick admin password reset script.
Run from project root: .venv\Scripts\python.exe reset_admin.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock hdbcli since we only need SQL Server
from unittest.mock import MagicMock
sys.modules.setdefault('hdbcli', MagicMock())
sys.modules.setdefault('hdbcli.dbapi', MagicMock())

from app import create_app

app = create_app()
with app.app_context():
    um = app.user_manager
    print(f"Users loaded: {list(um.users.keys())}")
    
    admin = um.users.get('admin')
    if admin:
        # Reset password
        success, msg = um.update_user('admin', password='admin123')
        if success:
            admin['must_change_password'] = False
            um._save_user_to_sql(admin)
            print(f"Admin password reset to 'admin123'")
            print(f"must_change_password = False")
        else:
            print(f"Failed: {msg}")
    else:
        print("No admin user found - creating one")
        um._create_default_admin()
    
    # Verify auth works
    ok = um.authenticate('admin', 'admin123')
    print(f"Auth test with admin/admin123: {'OK' if ok else 'FAILED'}")
