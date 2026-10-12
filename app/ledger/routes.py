"""记账业务蓝图：概览、流水、增删改、分类、账户、预算、CSV 导出。"""
from datetime import date, datetime
from urllib.parse import quote

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import Account, Budget, Category, Record
from ..services import (
    budget_status,
    build_record_query,
    category_options,
    ensure_user_defaults,
    overview,
    record_years,
    top_categories,
    validate_record_payload,
)
from ..utils import (
    ValidationError,
    build_records_csv,
    month_range,
    parse_amount,
    parse_int,
    shift_month,
)

ledger_bp = Blueprint("ledger", __name__)

ACCOUNT_KINDS = {
    "cash": "现金",
    "alipay": "支付宝",
    "wechat": "微信",
    "bank": "银行卡",
}
TYPE_LABELS = {"expense": "支出", "income": "收入"}


# ---------------------------------------------------------------------------
# 公共小工具
# ---------------------------------------------------------------------------
def _uid() -> int:
    return int(current_user.id)


def _parse_filters(args) -> dict:
    """解析 URL 上的筛选参数，非法值一律降级为空（不让坏参数把页面打挂）。"""
    filters = {}
    year = (args.get("year") or "").strip()
    filters["year"] = year if year.isdigit() and 2000 <= int(year) <= 2100 else ""

    month = (args.get("month") or "").strip()
    filters["month"] = month if month.isdigit() and 1 <= int(month) <= 12 else ""

    rtype = (args.get("type") or "").strip()
    filters["type"] = rtype if rtype in TYPE_LABELS else ""

    cid = (args.get("category_id") or "").strip()
    filters["category_id"] = cid if cid.isdigit() else ""

    filters["keyword"] = (args.get("keyword") or "").strip()[:50]
    return filters


def _month_label(filters: dict) -> str:
    if filters.get("year") and filters.get("month"):
        return f"{filters['year']}年{int(filters['month'])}月"
    if filters.get("year"):
        return f"{filters['year']}年"
    if filters.get("month"):
        return f"每年{int(filters['month'])}月"
    return "全部时间"


def _get_record_or_404(rid: int) -> Record:
    """按 id 查记录，并且必须属于当前用户——防止改 URL 就越权读写别人的账目。"""
    record = Record.query.filter_by(id=rid, user_id=_uid()).first()
    if record is None:
        abort(404)
    return record


def _record_form_context(record=None):
    """记账表单页的公共上下文（errors/values 由调用方单独传，默认空字典）。"""
    return {
        "record": record,
        "categories": category_options(_uid()),
        "accounts": Account.query.filter_by(user_id=_uid()).order_by(Account.id).all(),
        "is_edit": record is not None,
        "today_str": date.today().strftime("%Y-%m-%d"),
    }


def _validate_record_form(form):
    """服务端校验记账表单（规则集中在 services.validate_record_payload）。

    前端已经校验过一遍，这里再校验一遍——HTTP 请求可以绕过任何前端代码。
    """
    return validate_record_payload(_uid(), form)


# ---------------------------------------------------------------------------
# 概览首页
# ---------------------------------------------------------------------------
@ledger_bp.route("/")
@login_required
def index():
    today = date.today()
    data = overview(_uid(), today.year, today.month)
    recent = (
        Record.query.filter_by(user_id=_uid())
        .order_by(Record.record_date.desc(), Record.id.desc())
        .limit(8)
        .all()
    )
    return render_template(
        "ledger/index.html",
        summary=data,
        budget=data["budget"],
        recent_records=recent,
        top_categories=top_categories(_uid(), today.year, today.month)["items"],
        month_label=f"{today.year}年{today.month}月",
        categories=category_options(_uid()),
        accounts=Account.query.filter_by(user_id=_uid()).order_by(Account.id).all(),
        current_year=today.year,
        current_month=today.month,
        nav_active="index",
    )


# ---------------------------------------------------------------------------
# 流水列表
# ---------------------------------------------------------------------------
@ledger_bp.route("/records")
@login_required
def records():
    filters = _parse_filters(request.args)
    per_page = 10
    try:
        page = parse_int(request.args.get("page"), "页码", default=1)
    except ValidationError:
        # 页码被篡改（如 ?page=abc / ?page=-5）时兜底到第 1 页，而不是抛 500
        page = 1
        flash("页码参数不合法，已为你显示第 1 页", "warning")

    query = build_record_query(_uid(), filters)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # 当前筛选结果的收入/支出合计（同一个 WHERE 条件，只是去掉排序后聚合）
    rows = (
        query.order_by(None)
        .with_entities(Record.type, func.sum(Record.amount))
        .group_by(Record.type)
        .all()
    )
    income = next((round(float(total or 0), 2) for rtype, total in rows if rtype == "income"), 0.0)
    expense = next((round(float(total or 0), 2) for rtype, total in rows if rtype == "expense"), 0.0)

    return render_template(
        "ledger/records.html",
        pagination=pagination,
        records=pagination.items,
        filters=filters,
        categories=category_options(_uid()),
        years=record_years(_uid()),
        summary={
            "income": income,
            "expense": expense,
            "balance": round(income - expense, 2),
            "count": pagination.total,
        },
        month_label=_month_label(filters),
        per_page=per_page,
        nav_active="records",
    )


# ---------------------------------------------------------------------------
# 新增 / 编辑 / 删除
# ---------------------------------------------------------------------------
@ledger_bp.route("/records/create", methods=["GET", "POST"])
@login_required
def record_create():
    if request.method == "POST":
        data, errors = _validate_record_form(request.form)
        if not errors:
            record = Record(
                user_id=_uid(),
                amount=data["amount"],
                type=data["type"],
                category_id=data["category"].id if data["category"] else None,
                account_id=data["account"].id if data["account"] else None,
                record_date=data["record_date"],
                note=data["note"],
            )
            db.session.add(record)
            db.session.commit()
            flash(
                f"已记录{TYPE_LABELS[data['type']]} ¥{data['amount']:.2f}",
                "success",
            )
            return redirect(url_for("ledger.records"))
        flash("表单有错误，请检查后重新提交", "danger")
        return render_template(
            "ledger/record_form.html",
            errors=errors,
            values=request.form.to_dict(),
            action_url=url_for("ledger.record_create"),
            **_record_form_context(),
        )

    return render_template(
        "ledger/record_form.html",
        errors={},
        values={},
        action_url=url_for("ledger.record_create"),
        **_record_form_context(),
    )


@ledger_bp.route("/records/<int:rid>/edit", methods=["GET", "POST"])
@login_required
def record_edit(rid: int):
    record = _get_record_or_404(rid)
    if request.method == "POST":
        data, errors = _validate_record_form(request.form)
        if not errors:
            record.amount = data["amount"]
            record.type = data["type"]
            record.category_id = data["category"].id if data["category"] else None
            record.account_id = data["account"].id if data["account"] else None
            record.record_date = data["record_date"]
            record.note = data["note"]
            record.updated_at = datetime.now()
            db.session.commit()
            flash("修改已保存", "success")
            return redirect(url_for("ledger.records"))
        flash("表单有错误，请检查后重新提交", "danger")
        return render_template(
            "ledger/record_form.html",
            errors=errors,
            values=request.form.to_dict(),
            action_url=url_for("ledger.record_edit", rid=rid),
            **_record_form_context(record),
        )

    values = {
        "amount": f"{float(record.amount):.2f}",
        "type": record.type,
        "category_id": record.category_id or "",
        "account_id": record.account_id or "",
        "record_date": record.record_date.strftime("%Y-%m-%d"),
        "note": record.note or "",
    }
    return render_template(
        "ledger/record_form.html",
        errors={},
        values=values,
        action_url=url_for("ledger.record_edit", rid=rid),
        **_record_form_context(record),
    )


@ledger_bp.route("/records/<int:rid>/delete", methods=["POST"])
@login_required
def delete_record(rid: int):
    record = _get_record_or_404(rid)
    db.session.delete(record)
    db.session.commit()
    flash("记录已删除", "info")
    # 回到来源页（保留筛选条件），没有来源就回流水页
    return redirect(request.referrer or url_for("ledger.records"))


# ---------------------------------------------------------------------------
# 分类管理
# ---------------------------------------------------------------------------
@ledger_bp.route("/categories")
@login_required
def categories():
    all_cats = category_options(_uid())
    return render_template(
        "ledger/categories.html",
        expense_categories=[c for c in all_cats if c.type == "expense"],
        income_categories=[c for c in all_cats if c.type == "income"],
        errors={},
        values={},
        nav_active="categories",
    )


@ledger_bp.route("/categories/create", methods=["POST"])
@login_required
def create_category():
    errors, values = {}, request.form.to_dict()
    name = (request.form.get("name") or "").strip()
    ctype = (request.form.get("type") or "expense").strip()
    icon = (request.form.get("icon") or "💰").strip()[:8] or "💰"
    color = (request.form.get("color") or "#6366f1").strip()

    if not name:
        errors["name"] = "分类名称不能为空"
    elif len(name) > 20:
        errors["name"] = "分类名称最多 20 个字"
    if ctype not in TYPE_LABELS:
        errors["type"] = "收支类型不合法"
    if not color.startswith("#") or len(color) not in (4, 7):
        errors["color"] = "颜色值不合法"
    if not errors and Category.query.filter_by(user_id=_uid(), name=name, type=ctype).first():
        errors["name"] = "同类收支下已存在同名分类"

    if errors:
        all_cats = category_options(_uid())
        flash("新增分类失败：" + "；".join(errors.values()), "danger")
        return render_template(
            "ledger/categories.html",
            expense_categories=[c for c in all_cats if c.type == "expense"],
            income_categories=[c for c in all_cats if c.type == "income"],
            errors=errors,
            values=values,
            nav_active="categories",
        ), 400

    db.session.add(
        Category(user_id=_uid(), name=name, type=ctype, icon=icon, color=color, is_default=False)
    )
    db.session.commit()
    flash(f"分类「{name}」已添加", "success")
    return redirect(url_for("ledger.categories"))


@ledger_bp.route("/categories/<int:cid>/update", methods=["POST"])
@login_required
def update_category(cid: int):
    category = Category.query.filter_by(id=cid, user_id=_uid()).first_or_404()
    name = (request.form.get("name") or "").strip()
    icon = (request.form.get("icon") or category.icon).strip()[:8] or category.icon
    color = (request.form.get("color") or category.color).strip()
    if not name or len(name) > 20:
        flash("分类名称不能为空且不超过 20 个字", "danger")
        return redirect(url_for("ledger.categories"))
    duplicated = Category.query.filter(
        Category.user_id == _uid(),
        Category.name == name,
        Category.type == category.type,
        Category.id != category.id,
    ).first()
    if duplicated:
        flash("同类收支下已存在同名分类", "danger")
        return redirect(url_for("ledger.categories"))
    category.name, category.icon, category.color = name, icon, color
    db.session.commit()
    flash("分类已更新", "success")
    return redirect(url_for("ledger.categories"))


@ledger_bp.route("/categories/<int:cid>/delete", methods=["POST"])
@login_required
def delete_category(cid: int):
    category = Category.query.filter_by(id=cid, user_id=_uid()).first_or_404()
    if category.is_default:
        flash("系统预置分类不能删除，但可以改名或改颜色", "warning")
        return redirect(url_for("ledger.categories"))
    # 该分类下的历史账目保留，只是变为“未分类”（FK ON DELETE SET NULL）
    db.session.delete(category)
    db.session.commit()
    flash("分类已删除，原有账目保留为「未分类」", "info")
    return redirect(url_for("ledger.categories"))


# ---------------------------------------------------------------------------
# 账户管理
# ---------------------------------------------------------------------------
@ledger_bp.route("/accounts")
@login_required
def accounts():
    return render_template(
        "ledger/accounts.html",
        accounts=Account.query.filter_by(user_id=_uid()).order_by(Account.id).all(),
        account_kinds=ACCOUNT_KINDS,
        errors={},
        values={},
        nav_active="accounts",
    )


@ledger_bp.route("/accounts/create", methods=["POST"])
@login_required
def create_account():
    name = (request.form.get("name") or "").strip()
    kind = (request.form.get("kind") or "cash").strip()
    if not name or len(name) > 32:
        flash("账户名称不能为空且不超过 32 个字", "danger")
        return redirect(url_for("ledger.accounts"))
    if kind not in ACCOUNT_KINDS:
        flash("账户类型不合法", "danger")
        return redirect(url_for("ledger.accounts"))
    if Account.query.filter_by(user_id=_uid(), name=name).first():
        flash("已存在同名账户", "warning")
        return redirect(url_for("ledger.accounts"))
    db.session.add(Account(user_id=_uid(), name=name, kind=kind))
    db.session.commit()
    flash(f"账户「{name}」已添加", "success")
    return redirect(url_for("ledger.accounts"))


@ledger_bp.route("/accounts/<int:aid>/update", methods=["POST"])
@login_required
def update_account(aid: int):
    account = Account.query.filter_by(id=aid, user_id=_uid()).first_or_404()
    name = (request.form.get("name") or "").strip()
    kind = (request.form.get("kind") or account.kind).strip()
    if not name or len(name) > 32:
        flash("账户名称不能为空且不超过 32 个字", "danger")
        return redirect(url_for("ledger.accounts"))
    if kind not in ACCOUNT_KINDS:
        flash("账户类型不合法", "danger")
        return redirect(url_for("ledger.accounts"))
    # 新建时有唯一约束，改名时同样要判重，否则会撞 uq_account_user_name 直接 500
    duplicated = Account.query.filter(
        Account.user_id == _uid(), Account.name == name, Account.id != account.id
    ).first()
    if duplicated:
        flash("已存在同名账户", "warning")
        return redirect(url_for("ledger.accounts"))
    account.name, account.kind = name, kind
    db.session.commit()
    flash("账户已更新", "success")
    return redirect(url_for("ledger.accounts"))


@ledger_bp.route("/accounts/<int:aid>/delete", methods=["POST"])
@login_required
def delete_account(aid: int):
    account = Account.query.filter_by(id=aid, user_id=_uid()).first_or_404()
    if Account.query.filter_by(user_id=_uid()).count() <= 1:
        flash("至少保留一个账户", "warning")
        return redirect(url_for("ledger.accounts"))
    db.session.delete(account)
    db.session.commit()
    flash("账户已删除，原有账目保留（账户显示为空）", "info")
    return redirect(url_for("ledger.accounts"))


# ---------------------------------------------------------------------------
# 预算管理（加分项）
# ---------------------------------------------------------------------------
@ledger_bp.route("/budgets")
@login_required
def budgets():
    today = date.today()
    row = budget_status(_uid(), today.year, today.month)
    row.update({"year": today.year, "month": today.month})

    history = []
    for year, month in [shift_month(today.year, today.month, -i) for i in range(0, 6)]:
        item = budget_status(_uid(), year, month)
        item.update({"year": year, "month": month})
        history.append(item)

    return render_template(
        "ledger/budgets.html",
        budget_row=row,
        budget_history=history,
        current_year=today.year,
        current_month=today.month,
        nav_active="budgets",
    )


@ledger_bp.route("/budgets/save", methods=["POST"])
@login_required
def save_budget():
    try:
        year = parse_int(request.form.get("year"), "年份", minimum=2000, maximum=2100)
        month = parse_int(request.form.get("month"), "月份", minimum=1, maximum=12)
    except ValidationError as exc:
        flash(exc.message, "danger")
        return redirect(url_for("ledger.budgets"))

    raw_amount = (request.form.get("amount") or "").strip()
    # 金额填 0 或留空 = 取消该月预算
    if raw_amount in ("", "0", "0.00"):
        budget = Budget.query.filter_by(user_id=_uid(), year=year, month=month).first()
        if budget:
            db.session.delete(budget)
            db.session.commit()
            flash(f"{year}年{month}月的预算已取消", "info")
        else:
            flash("该月份还没有设置预算", "warning")
        return redirect(url_for("ledger.budgets"))

    try:
        amount = parse_amount(raw_amount, field="预算金额")
    except ValidationError as exc:
        flash(exc.message, "danger")
        return redirect(url_for("ledger.budgets"))

    budget = Budget.query.filter_by(user_id=_uid(), year=year, month=month).first()
    if budget is None:
        budget = Budget(user_id=_uid(), year=year, month=month, amount=amount)
        db.session.add(budget)
    else:
        budget.amount = amount
    db.session.commit()
    flash(f"{year}年{month}月的预算已设置为 ¥{amount:,.2f}", "success")
    return redirect(url_for("ledger.budgets"))


# ---------------------------------------------------------------------------
# CSV 导出（加分项）
# ---------------------------------------------------------------------------
@ledger_bp.route("/export.csv")
@login_required
def export_csv():
    filters = _parse_filters(request.args)
    rows = build_record_query(_uid(), filters).all()
    payload = build_records_csv(rows)
    filename = f"账目明细_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    # 中文文件名必须做百分号编码再放进 header：
    # HTTP 头按 ISO-8859-1 传输，直接塞中文会导致 werkzeug 抛
    # UnicodeEncodeError: 'latin-1' codec can't encode characters（test_client 校验不出来）
    encoded = quote(filename, safe="")
    return Response(
        payload,
        mimetype="text/csv",
        headers={
            # filename= 给老浏览器，filename*= 用 RFC 5987 编码给现代浏览器
            "Content-Disposition": f"attachment; filename=records.csv; filename*=UTF-8''{encoded}",
            "Cache-Control": "no-store",
        },
    )
