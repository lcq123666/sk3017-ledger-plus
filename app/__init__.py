"""应用工厂：创建并装配 Flask 应用。

使用工厂模式（create_app）而不是模块级全局 app，好处：
1. 测试时可以注入 TestConfig，得到独立的 app 与数据库；
2. 避免 extensions / models / routes 之间的循环导入；
3. 后续要做多实例（如命令行任务）不需要重复初始化。
"""
import logging
import mimetypes
import os
from datetime import date
from logging.handlers import RotatingFileHandler

# Windows 注册表里 .js 的 MIME 有时被登记成 text/plain，导致 Flask 静默模式
# 下静态脚本以 text/plain 返回（配合 X-Content-Type-Options 会被浏览器拒绝执行）。
# 这里强制登记正确的类型，保证 /static/js/*.js 永远按 JavaScript 下发。
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import CONFIG_MAP
from .extensions import csrf, db, login_manager


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(CONFIG_MAP.get(config_name, CONFIG_MAP["default"]))

    # 中文 JSON：默认 Flask 会把中文转成 \uXXXX，直接关掉保证接口可读
    app.json.ensure_ascii = False

    _init_extensions(app)
    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_cli(app)
    _configure_logging(app)

    with app.app_context():
        # 延迟导入，确保 db 已 init_app
        from .models import User  # noqa: F401
        from . import services  # noqa: F401

    return app


# ---------------------------------------------------------------------------
def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        """Flask-Login 通过 session 里的 id 还原用户对象。"""
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def unauthorized():
        """未登录：API 请求返回 401 JSON，页面请求跳登录页。

        关键点：Ajax 请求如果拿到 302 跳转，前端 fetch 会把登录页 HTML 当 JSON 解析，
        最终报 "Unexpected token '<'"，所以这里必须按请求类型分流。
        """
        if request.path.startswith("/api/") or _wants_json():
            return jsonify({"code": 1, "msg": "登录已过期，请重新登录"}), 401
        from flask import flash, redirect, request as req, url_for

        flash("请先登录后再继续操作。", "warning")
        return redirect(url_for("auth.login", next=req.full_path))


def _wants_json() -> bool:
    best = request.accept_mimetypes.best
    return best == "application/json" or request.is_json


def _register_blueprints(app: Flask) -> None:
    from .auth.routes import auth_bp
    from .errors import errors_bp
    from .ledger.routes import ledger_bp
    from .stats.routes import stats_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ledger_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(errors_bp)


def _register_template_helpers(app: Flask) -> None:
    from flask import request, url_for

    from .utils import fmt_date, fmt_money

    @app.template_filter("money")
    def _money(value):
        return fmt_money(value)

    @app.template_filter("datefmt")
    def _datefmt(value, fmt="%Y-%m-%d"):
        return fmt_date(value, fmt)

    @app.template_filter("signed_money")
    def _signed_money(value):
        """带正负号的金额：收入 +1,234.50 / 支出 -1,234.50。"""
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = 0.0
        return f"{'+' if num >= 0 else '-'}{abs(num):,.2f}"

    def _clean_args() -> dict:
        """把当前 URL 查询参数里"有值"的那些取出来（空值不拼进链接）。"""
        return {k: v for k, v in request.args.items() if v not in (None, "")}

    @app.template_global()
    def records_url(page=None, **kwargs):
        """生成保留当前筛选条件的分页链接。

        Jinja2 的 url_for 不支持 `**filters` 解包，所以在这里用 Python 统一拼，
        模板里只需写 {{ records_url(page=pagination.page + 1) }}。
        """
        args = _clean_args()
        args.update({k: v for k, v in kwargs.items() if v not in (None, "")})
        if page is not None:
            args["page"] = page
        return url_for("ledger.records", **args)

    @app.template_global()
    def export_url():
        """CSV 导出链接：沿用当前筛选条件，但不带页码。"""
        args = _clean_args()
        args.pop("page", None)
        return url_for("ledger.export_csv", **args)

    @app.template_global()
    def active_class(endpoint_prefix: str) -> str:
        """导航高亮：/records 与 /records/create 都算 records 模块。"""
        endpoint = request.endpoint or ""
        return "active" if endpoint.startswith(endpoint_prefix) else ""

    @app.context_processor
    def inject_globals():
        """所有模板都能拿到的基础变量。"""
        today = date.today()
        return {
            "today_date": today,
            "today_str": today.strftime("%Y-%m-%d"),
            "nav_year": today.year,
            "nav_month": today.month,
        }


def _register_error_handlers(app: Flask) -> None:
    def _is_api() -> bool:
        return request.path.startswith("/api/") or _wants_json()

    @app.errorhandler(400)
    def bad_request(error):
        if _is_api():
            return jsonify({"code": 1, "msg": "请求参数有误"}), 400
        return render_template("errors/400.html", message="请求参数有误"), 400

    @app.errorhandler(403)
    def forbidden(error):
        if _is_api():
            return jsonify({"code": 1, "msg": "没有权限执行该操作"}), 403
        return render_template("errors/403.html", message="没有权限访问该资源"), 403

    @app.errorhandler(404)
    def not_found(error):
        if _is_api():
            return jsonify({"code": 1, "msg": "资源不存在"}), 404
        return render_template("errors/404.html", message="页面走丢了"), 404

    @app.errorhandler(413)
    def too_large(error):
        if _is_api():
            return jsonify({"code": 1, "msg": "请求体过大"}), 413
        return render_template("errors/400.html", message="请求体过大"), 413

    @app.errorhandler(500)
    def server_error(error):
        # 出错时回滚未提交的事务，避免连接池里残留脏会话
        db.session.rollback()
        app.logger.exception("服务器内部错误: %s", error)
        if _is_api():
            return jsonify({"code": 1, "msg": "服务器开小差了，请稍后再试"}), 500
        return render_template("errors/500.html", message="服务器内部错误"), 500

    @app.errorhandler(HTTPException)
    def http_exception(error):
        """兜底：未单独处理的 HTTP 异常统一走这里，保证永远不返回裸 HTML 给接口。"""
        if _is_api():
            return jsonify({"code": 1, "msg": error.description}), error.code
        return render_template("errors/400.html", message=error.description), error.code

    @app.errorhandler(Exception)
    def uncaught(error):
        db.session.rollback()
        app.logger.exception("未捕获异常: %s", error)
        if _is_api():
            return jsonify({"code": 1, "msg": "服务器开小差了，请稍后再试"}), 500
        return render_template("errors/500.html", message="服务器内部错误"), 500


def _register_cli(app: Flask) -> None:
    from .cli import register_commands

    register_commands(app)


def _configure_logging(app: Flask) -> None:
    """日志同时写文件（logs/app.log，滚动到 1MB）和控制台。

    日志目录不可写（只读挂载、权限不足、沙箱限制等）时不能把应用带崩，
    因此这里降级为"仅控制台输出"，只在启动时打一条警告。
    """
    if app.config.get("TESTING"):
        return
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base_dir, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError as exc:  # pragma: no cover - 依赖运行环境的权限
        app.logger.warning("日志目录不可写（%s），已降级为仅控制台输出", exc)
        return

    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
    )
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
