"""通用工具：参数校验、日期区间、货币格式化、CSV 导出。

校验函数统一抛出 ValidationError，路由层捕获后转成友好的中文提示，
保证「服务端永远不信任前端」——前端做过校验，后端也要再做一遍。
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

# 金额：最多 8 位整数 + 最多 2 位小数，不允许负数/科学计数法
AMOUNT_RE = re.compile(r"^\d{1,8}(\.\d{1,2})?$")
# 日期：必须是补零的 YYYY-MM-DD
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 用户名：字母数字下划线，3~20 位
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$")
MONTH_RE = re.compile(r"^(0?[1-9]|1[0-2])$")

MAX_AMOUNT = 99999999.99
MIN_DATE = date(2000, 1, 1)


class ValidationError(Exception):
    """参数校验失败，message 会直接展示给用户。"""

    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.message = message
        self.field = field


# ---------------------------------------------------------------------------
# 单字段校验
# ---------------------------------------------------------------------------
def parse_amount(raw, field: str = "金额") -> float:
    """校验金额：非空、正数、最多两位小数。返回 float（入库用 Decimal(10,2)）。"""
    if raw is None:
        raise ValidationError(f"{field}不能为空", "amount")
    text = str(raw).strip()
    if not text:
        raise ValidationError(f"{field}不能为空", "amount")
    if not AMOUNT_RE.match(text):
        raise ValidationError(f"{field}格式不对：只能是正数且最多两位小数（如 12.50）", "amount")
    value = round(float(text), 2)
    if value <= 0:
        raise ValidationError(f"{field}必须大于 0", "amount")
    if value > MAX_AMOUNT:
        raise ValidationError(f"{field}超出上限（最大 {MAX_AMOUNT}）", "amount")
    return value


def parse_date(raw, field: str = "日期", allow_future: bool = False) -> date:
    """校验日期：格式 YYYY-MM-DD，范围 2000-01-01 ~ 今天（默认不允许未来日期）。

    先用正则卡死格式再交给 strptime：
    只靠 strptime 会放过 "2026-1-1"、"2026-01-1" 这类写法，
    同一个日期出现多种字符串形式会让后续按字符串比较/导出的逻辑变得不可预期。
    """
    text = (raw or "").strip()
    if not text:
        raise ValidationError(f"{field}不能为空", "record_date")
    if not DATE_RE.match(text):
        raise ValidationError(f"{field}格式不对，应为 YYYY-MM-DD", "record_date")
    try:
        value = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{field}格式不对，应为 YYYY-MM-DD", "record_date")
    if value < MIN_DATE:
        raise ValidationError(f"{field}不能早于 {MIN_DATE}", "record_date")
    if not allow_future and value > date.today():
        raise ValidationError(f"{field}不能晚于今天", "record_date")
    return value


def parse_type(raw, allowed=("expense", "income")) -> str:
    """校验收支类型，只接受白名单值（防越权写脏数据）。"""
    text = (raw or "").strip()
    if text not in allowed:
        raise ValidationError("收支类型不合法", "type")
    return text


def parse_int(raw, field: str, minimum: int = 1, maximum: int = 999999, default=None):
    """把 URL/表单参数安全转成整数。

    分页参数直接从 query string 拿，用户可能传 "abc" 或 "-1"，
    这里统一兜底，避免 int() 抛 ValueError 变成 500。
    """
    if raw is None or str(raw).strip() == "":
        if default is not None:
            return default
        raise ValidationError(f"{field}不能为空")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field}必须是整数")
    if value < minimum or value > maximum:
        raise ValidationError(f"{field}超出允许范围（{minimum} ~ {maximum}）")
    return value


def parse_note(raw, field: str = "备注", max_len: int = 200) -> str:
    text = (raw or "").strip()
    if len(text) > max_len:
        raise ValidationError(f"{field}最多 {max_len} 个字")
    return text


def parse_username(raw) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValidationError("用户名不能为空", "username")
    if not USERNAME_RE.match(text):
        raise ValidationError("用户名需为 2~20 位中英文、数字或下划线", "username")
    return text


def parse_password(raw) -> str:
    text = raw or ""
    if len(text) < 6:
        raise ValidationError("密码至少 6 位", "password")
    if len(text) > 64:
        raise ValidationError("密码最多 64 位", "password")
    return text


# ---------------------------------------------------------------------------
# 日期区间工具
# ---------------------------------------------------------------------------
def month_range(year: int, month: int):
    """返回某个月的第一天与最后一天（闭区间）。"""
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def shift_month(year: int, month: int, offset: int):
    """月份加减：shift_month(2026, 1, -1) -> (2025, 12)。"""
    index = (year * 12 + (month - 1)) + offset
    return index // 12, index % 12 + 1


def months_back(end_year: int, end_month: int, count: int = 6):
    """以 end 月为终点，向前取 count 个月，返回 [(year, month), ...] 升序。"""
    return [shift_month(end_year, end_month, i) for i in range(-(count - 1), 1)]


def today() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# 展示格式化（Jinja 过滤器）
# ---------------------------------------------------------------------------
def fmt_money(value) -> str:
    """千分位 + 两位小数：1234.5 -> 1,234.50。"""
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def fmt_date(value, fmt: str = "%Y-%m-%d") -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime(fmt)


# ---------------------------------------------------------------------------
# CSV 导出
# ---------------------------------------------------------------------------
def build_records_csv(records) -> bytes:
    """把记账记录导出成 CSV 字节流。

    关键点：UTF-8 编码 + 开头写入 BOM（\\ufeff），
    否则 Excel 用 GBK 解码会出现中文乱码。
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["日期", "类型", "分类", "账户", "金额", "备注"])
    for rec in records:
        writer.writerow(
            [
                rec.record_date.strftime("%Y-%m-%d"),
                "收入" if rec.type == "income" else "支出",
                rec.category.name if rec.category else "未分类",
                rec.account.name if rec.account else "",
                f"{float(rec.amount):.2f}",
                rec.note or "",
            ]
        )
    # utf-8-sig 会在写入时自动带上 BOM
    return buffer.getvalue().encode("utf-8-sig")
