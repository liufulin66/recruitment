"""应用工厂：组装配置、连接生命周期与路由，不在导入时操作数据库。"""

from datetime import timedelta
from pathlib import Path

from flask import Flask, redirect, request, session, url_for

import config
from db import close_db, get_connection

ROOT = Path(__file__).resolve().parent.parent


def init_database():
    """显式初始化业务表，不删除或重建现有表和数据。"""
    import auth
    import captcha
    from etl.schema import ensure_tables

    auth.ensure_users_table()
    captcha.ensure_captcha_table()
    conn = get_connection()
    try:
        ensure_tables(conn)
        conn.commit()
    finally:
        conn.close()


def create_app(test_config=None):
    app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
    app.config.from_mapping(
        SECRET_KEY=config.SECRET_KEY,
        DB=dict(config.DB),
        SESSION_COOKIE_SAMESITE=config.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_HTTPONLY=config.SESSION_COOKIE_HTTPONLY,
        PERMANENT_SESSION_LIFETIME=timedelta(days=config.REMEMBER_ME_DAYS),
        DEBUG=config.WEB_DEBUG,
    )
    if test_config:
        app.config.update(test_config)
    app.teardown_appcontext(close_db)

    from web.auth_routes import bp as auth_bp
    from web.dashboard import bp as dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    @app.before_request
    def require_login():
        endpoint = request.endpoint
        if endpoint is None:
            return None
        if endpoint in ("auth.login", "auth.register"):
            if session.get("user_id"):
                return redirect(url_for("dashboard.index"))
            return None
        if endpoint in ("static", "auth.captcha_image"):
            return None
        if not session.get("user_id"):
            target = request.full_path.rstrip("?")
            return redirect(url_for("auth.login", next=target))
        return None

    @app.context_processor
    def inject_common():
        return {
            "current_user": session.get("username"),
            "current_snapshot": None,
            "SALARY_NOTE": config.SALARY_NOTE,
        }

    @app.cli.command("init-db")
    def init_db_command():
        """创建认证、验证码与分析表（幂等，不删除数据）。"""
        init_database()
        print("Database tables initialized.")

    return app
