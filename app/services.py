"""业务逻辑层（Service）。

路由只负责「取参数 → 调 service → 渲染/返回 JSON」，
所有与数据库聚合、统计口径相关的代码集中在这里，好处是：
1. 同一个口径（例如"某月支出"）在首页、统计页、导出三处复用，不会各写一套；
2. 单元测试可以直接测 service，不必启动 HTTP 服务。
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func

from .extensions import db
from .models import Account, Budget, Category, Record, DEFAULT_ACCOUNTS, DEFAULT_CATEGORIES
from .utils import (
    ValidationError,
    month_range,
    months_back,
    parse_amount,
    parse_date,
    parse_note,
    parse_type,
)


def _f(value) -> float:
    """DECIMAL -> float（保留 2 位小数），None -> 0.0。

    数据库 SUM() 返回 Decimal，直接丢给 jsonify 会抛 TypeError；
    统一在这里转换，避免每个接口各转一次。
    """
    if value is None:
        return 0.0
    return round(float(value), 2)


def _percent(part, whole) -> float:
    """百分比：用 Decimal 做除法再四舍五入，避免 300.5/1000*100 得到 30.049999…。"""
    if not whole:
        return 0.0
    ratio = Decimal(str(part)) / Decimal(str(whole)) * Decimal("100")
    return float(ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _rate(current: float, previous: float):
    """环比/同比增长率（百分比）。上期为 0 时返回 None，前端显示“—”。"""
    if not previous:
        return None
    diff = Decimal(str(current)) - Decimal(str(previous))
    ratio = diff / Decimal(str(previous)) * Decimal("100")
    return float(ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# 初始化：新用户注册时复制一份系统预置分类 + 默认账户
# ---------------------------------------------------------------------------
def ensure_user_defaults(user) -> None:
    """为新用户创建预置分类与默认账户（幂等：已存在则跳过）。"""
    if not user.categories:
        for name, ctype, icon, color, order in DEFAULT_CATEGORIES:
            db.session.add(
                Category(
                    user_id=user.id,
                    name=name,
                    type=ctype,
                    icon=icon,
                    color=color,
                    is_default=True,
                    sort_order=order,
                )
            )
    if not user.accounts:
        for name, kind in DEFAULT_ACCOUNTS:
            db.session.add(Account(user_id=user.id, name=name, kind=kind))
    db.session.flush()


# ---------------------------------------------------------------------------
# 记账表单校验：页面表单与 Ajax 接口共用同一套规则
# ---------------------------------------------------------------------------
def validate_record_payload(user_id: int, payload) -> tuple:
    """校验一条记账数据，返回 (清洗后的数据, 错误字典)。

    payload 既可以是 request.form 也可以是 JSON dict；
    分类/账户必须属于当前用户，且分类类型必须与收支类型一致（防止构造请求写脏数据）。
    """
    errors, data = {}, {}
    try:
        data["amount"] = parse_amount(payload.get("amount"))
    except ValidationError as exc:
        errors["amount"] = exc.message
    try:
        data["type"] = parse_type(payload.get("type"))
    except ValidationError as exc:
        errors["type"] = exc.message
    try:
        data["record_date"] = parse_date(payload.get("record_date"))
    except ValidationError as exc:
        errors["record_date"] = exc.message
    try:
        data["note"] = parse_note(payload.get("note"))
    except ValidationError as exc:
        errors["note"] = exc.message

    category_id = str(payload.get("category_id") or "").strip()
    if category_id:
        category = Category.query.filter_by(id=category_id, user_id=user_id).first()
        if category is None:
            errors["category_id"] = "分类不存在或已被删除"
        elif data.get("type") and category.type != data["type"]:
            errors["category_id"] = "分类与收支类型不匹配"
        else:
            data["category"] = category
    else:
        data["category"] = None

    account_id = str(payload.get("account_id") or "").strip()
    if account_id:
        account = Account.query.filter_by(id=account_id, user_id=user_id).first()
        if account is None:
            errors["account_id"] = "账户不存在或已被删除"
        else:
            data["account"] = account
    else:
        data["account"] = None

    return data, errors


# ---------------------------------------------------------------------------
# 基础聚合：某日期区间的收入 / 支出 / 笔数
# ---------------------------------------------------------------------------
def period_totals(user_id: int, start: date, end: date):
    """按日期区间统计收入、支出与笔数。

    SQL: SELECT type, SUM(amount), COUNT(*) FROM record
         WHERE user_id=? AND record_date BETWEEN ? AND ? GROUP BY type
    只对 record_date 做区间比较、不在列上套函数，索引 (user_id, record_date) 可用。
    """
    rows = (
        db.session.query(Record.type, func.sum(Record.amount), func.count(Record.id))
        .filter(
            Record.user_id == user_id,
            Record.record_date >= start,
            Record.record_date <= end,
        )
        .group_by(Record.type)
        .all()
    )
    income = expense = 0.0
    count = 0
    for rtype, total, cnt in rows:
        count += int(cnt or 0)
        if rtype == "income":
            income = _f(total)
        else:
            expense = _f(total)
    return {"income": income, "expense": expense, "balance": round(income - expense, 2), "count": count}


def summary_for(user_id: int, year: int, month: int) -> dict:
    first, last = month_range(year, month)
    result = period_totals(user_id, first, last)
    result.update({"year": year, "month": month})
    return result


def budget_status(user_id: int, year: int, month: int, expense: float = None) -> dict:
    """预算执行情况：amount==0 表示没有设置预算，返回 amount=0、usage=0。"""
    budget = Budget.query.filter_by(user_id=user_id, year=year, month=month).first()
    amount = _f(budget.amount) if budget else 0.0
    if expense is None:
        first, last = month_range(year, month)
        expense = period_totals(user_id, first, last)["expense"]
    usage = _percent(expense, amount) if amount > 0 else 0.0
    if amount <= 0:
        level = "none"
    elif usage >= 100:
        level = "over"
    elif usage >= 80:
        level = "warn"
    else:
        level = "normal"
    return {
        "amount": amount,
        "spent": expense,
        "remain": round(amount - expense, 2),
        "usage": usage,
        "level": level,
    }


# ---------------------------------------------------------------------------
# 图表数据
# ---------------------------------------------------------------------------
def category_pie(user_id: int, year: int, month: int, ctype: str = "expense", limit: int = 12):
    """某月某类型下各分类的金额占比（饼图）。

    SQL: SELECT c.name, c.color, SUM(r.amount) FROM record r
         JOIN category c ON c.id = r.category_id
         WHERE r.user_id=? AND r.type=? AND r.record_date BETWEEN ? AND ?
         GROUP BY c.id ORDER BY SUM(r.amount) DESC
    占比在 Python 里用 Decimal->float 计算，避免 SQL 除法精度差异。
    """
    first, last = month_range(year, month)
    rows = (
        db.session.query(
            Category.id, Category.name, Category.color, func.sum(Record.amount).label("total")
        )
        .join(Record, Record.category_id == Category.id)
        .filter(
            Record.user_id == user_id,
            Record.type == ctype,
            Record.record_date >= first,
            Record.record_date <= last,
        )
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.sum(Record.amount).desc())
        .all()
    )
    items = []
    grand_total = 0.0
    for cid, name, color, total in rows:
        value = _f(total)
        grand_total += value
        # id 供前端"点击扇区 → 按分类筛选日趋势"联动使用
        items.append({"id": cid, "name": name, "color": color, "value": value})
    # 分类过多的尾部合并为“其他”，保证饼图可读
    if len(items) > limit:
        head, tail = items[: limit - 1], items[limit - 1 :]
        head.append(
            {
                "id": None,
                "name": "其他",
                "color": "#94a3b8",
                "value": round(sum(i["value"] for i in tail), 2),
            }
        )
        items = head
    for item in items:
        item["percent"] = _percent(item["value"], grand_total)
    return {"items": items, "total": round(grand_total, 2)}


def monthly_trend(user_id: int, end_year: int, end_month: int, months: int = 6):
    """近 N 个月收入/支出对比（并列柱状图）。

    逐月做一次区间聚合（6 次小查询，单次都走 (user_id, record_date) 索引），
    与用 YEAR()/MONTH() 分组相比：索引友好、跨数据库方言可移植（MySQL/SQLite 测试）。
    """
    labels, incomes, expenses = [], [], []
    for year, month in months_back(end_year, end_month, months):
        first, last = month_range(year, month)
        totals = period_totals(user_id, first, last)
        labels.append(f"{year}-{month:02d}")
        incomes.append(totals["income"])
        expenses.append(totals["expense"])
    return {"labels": labels, "income": incomes, "expense": expenses}


def daily_trend(user_id: int, year: int, month: int, category_id: int = None):
    """当月每日收入/支出（折线图）。

    SQL: SELECT record_date, type, SUM(amount) FROM record
         WHERE user_id=? AND record_date BETWEEN ? AND ? [AND category_id=?]
         GROUP BY record_date, type
    没有记录的日期补 0（前端折线不会断点、不会出现 NaN）。
    """
    first, last = month_range(year, month)
    query = db.session.query(
        Record.record_date, Record.type, func.sum(Record.amount)
    ).filter(
        Record.user_id == user_id,
        Record.record_date >= first,
        Record.record_date <= last,
    )
    if category_id:
        query = query.filter(Record.category_id == category_id)
    rows = query.group_by(Record.record_date, Record.type).all()

    expense_map, income_map = {}, {}
    for day, rtype, total in rows:
        if rtype == "income":
            income_map[day] = _f(total)
        else:
            expense_map[day] = _f(total)

    labels, expenses, incomes = [], [], []
    cursor = first
    while cursor <= last:
        labels.append(cursor.strftime("%m-%d"))
        expenses.append(expense_map.get(cursor, 0.0))
        incomes.append(income_map.get(cursor, 0.0))
        cursor += timedelta(days=1)
    return {"labels": labels, "expense": expenses, "income": incomes}


def heatmap(user_id: int, year: int):
    """年度日历热力图：每天的总支出。

    SQL: SELECT record_date, SUM(amount) FROM record
         WHERE user_id=? AND type='expense' AND record_date BETWEEN ? AND ?
         GROUP BY record_date
    """
    first, last = date(year, 1, 1), date(year, 12, 31)
    rows = (
        db.session.query(Record.record_date, func.sum(Record.amount))
        .filter(
            Record.user_id == user_id,
            Record.type == "expense",
            Record.record_date >= first,
            Record.record_date <= last,
        )
        .group_by(Record.record_date)
        .all()
    )
    values = [[day.isoformat(), _f(total)] for day, total in rows]
    max_value = max([v[1] for v in values], default=0.0)
    return {"year": year, "max": round(max_value, 2), "values": values}


def top_categories(user_id: int, year: int, month: int, ctype: str = "expense", limit: int = 5):
    """某月支出 TOP N 分类（横向条形图）。"""
    data = category_pie(user_id, year, month, ctype, limit=50)
    items = data["items"][:limit]
    return {"items": items}


# ---------------------------------------------------------------------------
# 概览（首页 / 统计页指标卡）
# ---------------------------------------------------------------------------
def overview(user_id: int, year: int, month: int) -> dict:
    """当月汇总 + 环比（上月）/ 同比（去年同月）+ 预算执行。"""
    current = summary_for(user_id, year, month)

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    prev = summary_for(user_id, prev_year, prev_month)
    last_year = summary_for(user_id, year - 1, month)

    mom = {
        "expense_rate": _rate(current["expense"], prev["expense"]),
        "income_rate": _rate(current["income"], prev["income"]),
        "balance_rate": _rate(current["balance"], prev["balance"]),
    }
    yoy = {
        "expense_rate": _rate(current["expense"], last_year["expense"]),
        "income_rate": _rate(current["income"], last_year["income"]),
    }
    budget = budget_status(user_id, year, month, current["expense"])
    return {**current, "mom": mom, "yoy": yoy, "budget": budget}


# ---------------------------------------------------------------------------
# 列表查询（流水页 / CSV 导出共用同一套筛选条件）
# ---------------------------------------------------------------------------
def build_record_query(user_id: int, filters: dict):
    """根据筛选条件构造查询。

    参数 filters: year/month/type/category_id/keyword，均可为空。
    返回未分页的 Query 对象，列表页用 .paginate()，导出用 .all()。
    """
    query = Record.query.filter(Record.user_id == user_id)

    year, month = filters.get("year"), filters.get("month")
    if year and month:
        first, last = month_range(int(year), int(month))
        query = query.filter(Record.record_date >= first, Record.record_date <= last)
    elif year:
        query = query.filter(
            Record.record_date >= date(int(year), 1, 1),
            Record.record_date <= date(int(year), 12, 31),
        )
    elif month:
        # 只选了月份：取最近一年内该月的全部记录（跨年也适用）
        today = date.today()
        year_now = today.year
        first, last = month_range(year_now, int(month))
        query = query.filter(Record.record_date >= first, Record.record_date <= last)

    if filters.get("type") in ("income", "expense"):
        query = query.filter(Record.type == filters["type"])
    if filters.get("category_id"):
        query = query.filter(Record.category_id == int(filters["category_id"]))
    keyword = (filters.get("keyword") or "").strip()
    if keyword:
        # 用参数化的 LIKE，SQLAlchemy 会自动转义，不存在拼接 SQL 注入
        query = query.filter(Record.note.like(f"%{keyword}%"))
    return query.order_by(Record.record_date.desc(), Record.id.desc())


def category_options(user_id: int, ctype: str = None):
    query = Category.query.filter_by(user_id=user_id)
    if ctype:
        query = query.filter_by(type=ctype)
    return query.order_by(Category.type, Category.sort_order, Category.id).all()


def record_years(user_id: int):
    """用户有记录的年份列表（降序），供筛选下拉框使用。"""
    rows = (
        db.session.query(Record.record_date)
        .filter(Record.user_id == user_id)
        .order_by(Record.record_date.desc())
        .all()
    )
    years = {day.year for (day,) in rows}
    years.add(date.today().year)
    return sorted(years, reverse=True)
