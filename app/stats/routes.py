"""统计与图表数据接口蓝图。

页面 GET /stats 只负责渲染骨架，数据全部由 /api/stats/* 返回 JSON，
前端 ECharts 通过 fetch 拉取 —— 这样切换筛选条件时不用整页刷新。
"""
from datetime import date

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Record
from ..services import (
    category_pie,
    daily_trend,
    heatmap,
    monthly_trend,
    overview,
    record_years,
    top_categories,
    validate_record_payload,
)

stats_bp = Blueprint("stats", __name__)


# ---------------------------------------------------------------------------
# 参数解析与统一响应
# ---------------------------------------------------------------------------
def _json_ok(data=None, msg="ok"):
    return jsonify({"code": 0, "msg": msg, "data": data})


def _json_error(msg: str, status: int = 400, field: str = None):
    payload = {"code": 1, "msg": msg}
    if field:
        payload["field"] = field
    return jsonify(payload), status


class ApiParamError(Exception):
    def __init__(self, msg: str, field: str = None):
        self.msg = msg
        self.field = field


def _int_arg(name: str, default=None, minimum: int = 1, maximum: int = 999999) -> int:
    """读取整数型查询参数；不合法时抛 ApiParamError（由蓝图错误处理器转 400 JSON）。"""
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        if default is None:
            raise ApiParamError(f"缺少参数 {name}", name)
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiParamError(f"参数 {name} 必须是整数", name)
    if value < minimum or value > maximum:
        raise ApiParamError(f"参数 {name} 超出范围（{minimum}~{maximum}）", name)
    return value


def _year_month():
    today = date.today()
    year = _int_arg("year", today.year, 2000, 2100)
    month = _int_arg("month", today.month, 1, 12)
    return year, month


@stats_bp.errorhandler(ApiParamError)
def _handle_api_param_error(exc: ApiParamError):
    return _json_error(exc.msg, 400, exc.field)


# ---------------------------------------------------------------------------
# 统计页面
# ---------------------------------------------------------------------------
@stats_bp.route("/stats")
@login_required
def index():
    today = date.today()
    return render_template(
        "stats/index.html",
        years=record_years(int(current_user.id)),
        current_year=today.year,
        current_month=today.month,
        nav_active="stats",
    )


# ---------------------------------------------------------------------------
# 统计接口
# ---------------------------------------------------------------------------
@stats_bp.route("/api/stats/overview")
@login_required
def api_overview():
    year, month = _year_month()
    return _json_ok(overview(int(current_user.id), year, month))


@stats_bp.route("/api/stats/category-pie")
@login_required
def api_category_pie():
    year, month = _year_month()
    ctype = request.args.get("type", "expense")
    if ctype not in ("expense", "income"):
        raise ApiParamError("参数 type 只能是 expense 或 income", "type")
    return _json_ok(category_pie(int(current_user.id), year, month, ctype))


@stats_bp.route("/api/stats/monthly-trend")
@login_required
def api_monthly_trend():
    today = date.today()
    end_year = _int_arg("end_year", today.year, 2000, 2100)
    end_month = _int_arg("end_month", today.month, 1, 12)
    months = _int_arg("months", 6, 1, 24)
    return _json_ok(monthly_trend(int(current_user.id), end_year, end_month, months))


@stats_bp.route("/api/stats/daily-trend")
@login_required
def api_daily_trend():
    year, month = _year_month()
    category_id = request.args.get("category_id", "").strip()
    if category_id:
        try:
            category_id = int(category_id)
        except ValueError:
            raise ApiParamError("参数 category_id 必须是整数", "category_id")
    else:
        category_id = None
    return _json_ok(daily_trend(int(current_user.id), year, month, category_id))


@stats_bp.route("/api/stats/heatmap")
@login_required
def api_heatmap():
    today = date.today()
    year = _int_arg("year", today.year, 2000, 2100)
    return _json_ok(heatmap(int(current_user.id), year))


@stats_bp.route("/api/stats/top-categories")
@login_required
def api_top_categories():
    year, month = _year_month()
    ctype = request.args.get("type", "expense")
    if ctype not in ("expense", "income"):
        raise ApiParamError("参数 type 只能是 expense 或 income", "type")
    limit = _int_arg("limit", 5, 1, 20)
    return _json_ok(top_categories(int(current_user.id), year, month, ctype, limit))


# ---------------------------------------------------------------------------
# Ajax 快速记账
# ---------------------------------------------------------------------------
@stats_bp.route("/api/records", methods=["POST"])
@login_required
def api_create_record():
    """不刷新页面记一笔账。前端要求带 X-CSRFToken 头，缺失会被 CSRFProtect 拦下。"""
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict()
    data, errors = validate_record_payload(int(current_user.id), payload)
    if errors:
        first_field = next(iter(errors))
        return _json_error(errors[first_field], 400, first_field)

    record = Record(
        user_id=int(current_user.id),
        amount=data["amount"],
        type=data["type"],
        category_id=data["category"].id if data["category"] else None,
        account_id=data["account"].id if data["account"] else None,
        record_date=data["record_date"],
        note=data["note"],
    )
    db.session.add(record)
    db.session.commit()
    return _json_ok(record.to_dict(), "记账成功")
