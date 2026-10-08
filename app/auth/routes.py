"""认证蓝图：注册 / 登录 / 退出。"""
from urllib.parse import urlparse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from ..services import ensure_user_defaults
from ..utils import ValidationError, parse_password, parse_username

auth_bp = Blueprint("auth", __name__)


def _safe_next(target: str):
    """只允许跳回本站地址，防止「开放重定向」漏洞（钓鱼链接常拿 next= 做文章）。"""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/"):
        return None
    return target


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("ledger.index"))

    errors, values = {}, {}
    if request.method == "POST":
        values = request.form.to_dict()
        try:
            username = parse_username(request.form.get("username"))
            password = parse_password(request.form.get("password"))
            confirm = request.form.get("confirm_password") or ""
            nickname = (request.form.get("nickname") or "").strip()[:32] or username

            if password != confirm:
                errors["confirm_password"] = "两次输入的密码不一致"
            if User.query.filter_by(username=username).first():
                errors["username"] = "该用户名已被注册，换一个试试"

            if not errors:
                user = User(username=username, nickname=nickname)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()  # 先拿到 user.id，再生成默认分类/账户
                ensure_user_defaults(user)
                db.session.commit()
                flash("注册成功，请登录后开始记账～", "success")
                return redirect(url_for("auth.login"))
        except ValidationError as exc:
            errors[exc.field or "_form"] = exc.message
        except Exception:  # 数据库异常等，回滚并给用户可读提示
            db.session.rollback()
            raise

    return render_template("auth/register.html", errors=errors, values=values)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("ledger.index"))

    errors, values = {}, {}
    if request.method == "POST":
        values = {"username": request.form.get("username", "")}
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(username=username).first()
        # 用户名不存在与密码错误给同一句提示，避免泄露"哪些账号存在"
        if not user or not user.check_password(password):
            errors["_form"] = "用户名或密码错误"
        else:
            login_user(user, remember=remember)
            flash(f"欢迎回来，{user.nickname}！", "success")
            return redirect(_safe_next(request.args.get("next")) or url_for("ledger.index"))

    return render_template("auth/login.html", errors=errors, values=values)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已安全退出登录", "info")
    return redirect(url_for("auth.login"))
