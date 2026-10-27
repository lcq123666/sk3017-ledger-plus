"""记账条目测试：增删改查、筛选、分页、越权、CSV 导出。"""
from datetime import date, timedelta

from app.extensions import db
from app.models import Record, User
from tests.conftest import PASSWORD, category_by_name, make_record


def test_index_ok(auth_client):
    response = auth_client.get("/")
    assert response.status_code == 200


def test_create_record_success(auth_client, demo):
    category = category_by_name(demo.id, "餐饮")
    response = auth_client.post(
        "/records/create",
        data={
            "amount": "25.50",
            "type": "expense",
            "category_id": category.id,
            "account_id": "",
            "record_date": date.today().strftime("%Y-%m-%d"),
            "note": "食堂午饭",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    record = Record.query.filter_by(user_id=demo.id, note="食堂午饭").first()
    assert record is not None
    assert float(record.amount) == 25.50


def test_create_record_invalid_amount(auth_client, demo):
    category = category_by_name(demo.id, "餐饮")
    response = auth_client.post(
        "/records/create",
        data={
            "amount": "abc",
            "type": "expense",
            "category_id": category.id,
            "record_date": date.today().strftime("%Y-%m-%d"),
        },
    )
    # 校验失败：返回 200 并回显错误（不重定向），DB 里不应有脏数据
    assert response.status_code == 200
    assert "金额格式不对" in response.get_data(as_text=True)
    assert Record.query.count() == 0


def test_create_record_empty_amount(auth_client, demo):
    response = auth_client.post(
        "/records/create",
        data={
            "amount": "",
            "type": "expense",
            "record_date": date.today().strftime("%Y-%m-%d"),
        },
    )
    assert response.status_code == 200
    assert "不能为空" in response.get_data(as_text=True)


def test_create_record_future_date(auth_client, demo):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    response = auth_client.post(
        "/records/create",
        data={"amount": "10.00", "type": "expense", "record_date": tomorrow},
    )
    assert response.status_code == 200
    assert "不能晚于今天" in response.get_data(as_text=True)


def test_create_record_wrong_category_type(auth_client, demo):
    """分类类型与收支类型不匹配时必须拒绝（防止构造请求写脏数据）。"""
    income_category = category_by_name(demo.id, "工资")
    response = auth_client.post(
        "/records/create",
        data={
            "amount": "10.00",
            "type": "expense",
            "category_id": income_category.id,
            "record_date": date.today().strftime("%Y-%m-%d"),
        },
    )
    assert response.status_code == 200
    assert "不匹配" in response.get_data(as_text=True)


def test_create_record_unknown_category(auth_client):
    response = auth_client.post(
        "/records/create",
        data={
            "amount": "10.00",
            "type": "expense",
            "category_id": 99999,
            "record_date": date.today().strftime("%Y-%m-%d"),
        },
    )
    assert response.status_code == 200
    assert "分类不存在" in response.get_data(as_text=True)


def test_edit_record(auth_client, demo):
    record = make_record(demo.id, "10.00", "expense", "餐饮", date.today(), "旧备注")
    category = category_by_name(demo.id, "交通")
    response = auth_client.post(
        f"/records/{record.id}/edit",
        data={
            "amount": "88.88",
            "type": "expense",
            "category_id": category.id,
            "record_date": date.today().strftime("%Y-%m-%d"),
            "note": "新备注",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    updated = db.session.get(Record, record.id)
    assert float(updated.amount) == 88.88
    assert updated.note == "新备注"
    assert updated.category.name == "交通"


def test_delete_record(auth_client, demo):
    record = make_record(demo.id, "10.00", "expense", "餐饮", date.today())
    response = auth_client.post(f"/records/{record.id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert db.session.get(Record, record.id) is None


def test_delete_other_users_record_404(auth_client, app, demo):
    """换个用户登录后改 URL 也删不到别人的记录（越权防护）。"""
    other = User(username="other", nickname="别人")
    other.set_password(PASSWORD)
    db.session.add(other)
    db.session.commit()
    record = make_record(other.id, "10.00", "expense", "餐饮", date.today())

    response = auth_client.post(f"/records/{record.id}/delete")
    assert response.status_code == 404
    assert db.session.get(Record, record.id) is not None


def test_records_filter_by_type(auth_client, demo, sample_records):
    response = auth_client.get("/records?type=expense")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "食堂午饭" in text
    # 收入记录不应出现在支出筛选结果里
    assert "实习补贴" not in text


def test_records_filter_by_keyword(auth_client, demo, sample_records):
    response = auth_client.get("/records?keyword=高铁")
    text = response.get_data(as_text=True)
    assert "高铁票" in text
    assert "食堂午饭" not in text


def test_records_filter_by_month(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    response = auth_client.get(f"/records?year={year}&month={month}")
    text = response.get_data(as_text=True)
    assert "食堂午饭" in text
    assert "上月聚餐" not in text


def test_records_invalid_page_falls_back(auth_client, demo):
    """?page=abc 这种篡改不能导致 500，应降级到第 1 页并提示。"""
    for bad in ["abc", "-5", "0", "1.5", ""]:
        response = auth_client.get(f"/records?page={bad}")
        assert response.status_code == 200, bad


def test_records_pagination(auth_client, demo):
    for i in range(15):
        make_record(demo.id, "1.%02d" % i, "expense", "餐饮", date.today(), f"第{i}条")
    first = auth_client.get("/records?page=1")
    second = auth_client.get("/records?page=2")
    assert first.status_code == 200 and second.status_code == 200
    # 按日期倒序 + id 倒序：第 1 页是第 14~5 条，第 2 页是第 4~0 条
    first_text = first.get_data(as_text=True)
    second_text = second.get_data(as_text=True)
    assert "第14条" in first_text
    assert "第0条" not in first_text
    assert "第0条" in second_text


def test_keyword_sql_injection_is_safe(auth_client, demo, sample_records):
    """关键词里带 SQL 特殊字符只能当普通文本处理，不能把表删了/拖垮。"""
    payload = "' OR 1=1 -- "
    response = auth_client.get("/records", query_string={"keyword": payload})
    assert response.status_code == 200
    assert Record.query.count() == 4


def test_export_csv_bom(auth_client, demo, sample_records):
    response = auth_client.get("/export.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.data.startswith(b"\xef\xbb\xbf")
    text = response.data.decode("utf-8-sig")
    # 表头 + 4 条记录
    assert len([line for line in text.strip().splitlines() if line]) == 5


def test_export_csv_respects_filters(auth_client, sample_records):
    response = auth_client.get("/export.csv?type=income")
    text = response.data.decode("utf-8-sig")
    assert "收入" in text
    assert "食堂午饭" not in text


def test_record_form_pages(auth_client):
    assert auth_client.get("/records/create").status_code == 200
