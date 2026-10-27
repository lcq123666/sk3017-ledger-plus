"""参数校验单元测试：金额、日期、页码、用户名、密码。

这些规则是「服务端不信任前端」的最后一道防线，必须单独覆盖，
因为页面上的 JS 校验绕过去太容易了（改一下请求就行）。
"""
from datetime import date, timedelta

import pytest

from app.utils import (
    ValidationError,
    build_records_csv,
    fmt_money,
    month_range,
    months_back,
    parse_amount,
    parse_date,
    parse_int,
    parse_note,
    parse_type,
    parse_username,
    shift_month,
)


class TestParseAmount:
    @pytest.mark.parametrize("raw,expected", [("12", 12.0), ("12.5", 12.5), ("12.50", 12.5), ("0.01", 0.01), ("99999999.99", 99999999.99)])
    def test_valid_amount(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize("raw", ["", "  ", None, "abc", "-5", "0", "0.00", "12.345", "1e5", " 1 2 ", "999999999.99"])
    def test_invalid_amount(self, raw):
        with pytest.raises(ValidationError):
            parse_amount(raw)

    def test_error_message_is_user_friendly(self):
        with pytest.raises(ValidationError) as exc:
            parse_amount("abc")
        assert "格式" in exc.value.message
        assert exc.value.field == "amount"


class TestParseDate:
    def test_valid_date(self):
        assert parse_date("2026-10-01") == date(2026, 10, 1)

    @pytest.mark.parametrize("raw", ["", "2026/10/01", "2026-13-01", "2026-02-30", "abc", "2026-1-1"])
    def test_invalid_format(self, raw):
        with pytest.raises(ValidationError):
            parse_date(raw)

    def test_future_date_rejected(self):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        with pytest.raises(ValidationError) as exc:
            parse_date(tomorrow)
        assert "今天" in exc.value.message

    def test_allow_future_flag(self):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert parse_date(tomorrow, allow_future=True) == date.today() + timedelta(days=1)

    def test_too_old_date_rejected(self):
        with pytest.raises(ValidationError):
            parse_date("1999-12-31")


class TestParseOthers:
    def test_parse_int_default(self):
        assert parse_int(None, "页码", default=1) == 1
        assert parse_int("3", "页码") == 3

    @pytest.mark.parametrize("raw", ["abc", "1.5", "-1", "0", "99999999"])
    def test_parse_int_invalid(self, raw):
        with pytest.raises(ValidationError):
            parse_int(raw, "页码")

    def test_parse_int_range(self):
        assert parse_int("12", "月份", minimum=1, maximum=12) == 12
        with pytest.raises(ValidationError):
            parse_int("13", "月份", minimum=1, maximum=12)

    def test_parse_type_whitelist(self):
        assert parse_type("expense") == "expense"
        assert parse_type("income") == "income"
        with pytest.raises(ValidationError):
            parse_type("transfer")

    def test_parse_username(self):
        assert parse_username(" 小明_2026 ") == "小明_2026"
        for bad in ["", "a", "x" * 21, "bad name", "name<script>"]:
            with pytest.raises(ValidationError):
                parse_username(bad)

    def test_parse_note(self):
        assert parse_note("  午饭  ") == "午饭"
        with pytest.raises(ValidationError):
            parse_note("超" * 201)


class TestDateHelpers:
    def test_month_range(self):
        assert month_range(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
        assert month_range(2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))
        assert month_range(2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))

    def test_shift_month(self):
        assert shift_month(2026, 1, -1) == (2025, 12)
        assert shift_month(2026, 12, 1) == (2027, 1)
        assert shift_month(2026, 10, -10) == (2025, 12)

    def test_months_back(self):
        assert months_back(2026, 3, 6) == [
            (2025, 10),
            (2025, 11),
            (2025, 12),
            (2026, 1),
            (2026, 2),
            (2026, 3),
        ]

    def test_fmt_money(self):
        assert fmt_money(1234.5) == "1,234.50"
        assert fmt_money(None) == "0.00"
        assert fmt_money("abc") == "0.00"


class TestCsvExport:
    def test_csv_has_utf8_bom(self, app, demo):
        from .conftest import make_record

        make_record(demo.id, "12.30", "expense", "餐饮", date.today(), "备注里有中文")
        from app.models import Record

        payload = build_records_csv(Record.query.all())
        assert payload.startswith(b"\xef\xbb\xbf"), "缺少 UTF-8 BOM，Excel 打开会中文乱码"
        text = payload.decode("utf-8-sig")
        assert "日期,类型,分类,账户,金额,备注" in text
        assert "备注里有中文" in text
        assert "12.30" in text
