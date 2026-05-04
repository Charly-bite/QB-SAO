"""
Request Logger Middleware
"""
import time
import logging
from flask import request, g
from flask_login import current_user

logger = logging.getLogger('seguimiento.requests')


def init_request_logger(app):
    @app.before_request
    def _start_timer():
        g.request_start_time = time.time()

    @app.after_request
    def _log_request(response):
        if request.path.startswith('/static/') or request.path == '/favicon.ico':
            return response

        duration_ms = round((time.time() - getattr(g, 'request_start_time', time.time())) * 1000, 1)

        user = 'anonymous'
        if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            user = getattr(current_user, 'username', str(current_user.get_id()))

        status = response.status_code
        log_fn = logger.error if status >= 500 else (logger.warning if status >= 400 else logger.info)
        log_fn('%s %s → %d (%sms) [user=%s, ip=%s]', request.method, request.path, status, duration_ms, user, request.remote_addr)

        return response
