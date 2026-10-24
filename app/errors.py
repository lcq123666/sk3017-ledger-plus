"""错误页蓝图。

Flask-WTF 的 CSRF 校验失败时会跳转到 WTF_CSRF_FAILURE_VIEW 指定的端点，
这里提供 errors.csrf_error，给出「页面停留过久/令牌失效」的友好提示而不是裸 400。
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

errors_bp = Blueprint("errors", __name__)


@errors_bp.route("/csrf-error")
def csrf_error():
    if request.path.startswith("/api/") or request.is_json:
        from flask import jsonify

        return jsonify({"code": 1, "msg": "表单令牌已失效，请刷新页面后重试"}), 400
    flash("表单令牌已失效（可能是页面停留过久），请刷新页面后重新提交。", "warning")
    return render_template("errors/400.html", message="表单令牌已失效"), 400


@errors_bp.route("/healthz")
def healthz():
    """健康检查：部署后可用来确认应用与数据库都活着。"""
    from sqlalchemy import text

    from .extensions import db

    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # pragma: no cover
        return {"status": "error", "db": str(exc)}, 503
