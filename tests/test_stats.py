"""统计接口与预算功能测试。

重点验证「聚合数字对不对」而不是"页面能不能打开"：
期望值都用固定的样本数据（见 conftest.sample_records）算好，避免出现"接口返回 0 也算通过"的假测试。
"""
import calendar
from datetime import date

import pytest

from app.extensions import db
from app.models import Budget, Record
from tests.conftest import category_by_name, make_record


def test_stats_page_ok(auth_client):
    assert auth_client.get("/stats").status_code == 200


def test_overview_numbers(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    response = auth_client.get(f"/api/stats/overview?year={year}&month={month}")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["expense"] == 300.50
    assert data["income"] == 1000.00
    assert data["balance"] == 699.50
    assert data["count"] == 3
    # 上月支出 50.25 → 环比 (300.50-50.25)/50.25*100 ≈ 498.0%
    assert data["mom"]["expense_rate"] == pytest.approx(498.0, abs=0.2)


def test_overview_empty_month(auth_client):
    """没有任何数据的月份不能报错，各项应为 0、环比为 None。"""
    response = auth_client.get("/api/stats/overview?year=2020&month=1")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["expense"] == 0
    assert data["income"] == 0
    assert data["count"] == 0
    assert data["mom"]["expense_rate"] is None
    assert data["budget"]["level"] == "none"


def test_category_pie(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    data = auth_client.get(f"/api/stats/category-pie?year={year}&month={month}").get_json()["data"]
    assert data["total"] == 300.50
    names = [item["name"] for item in data["items"]]
    assert names == ["交通", "餐饮"]
    assert data["items"][0]["value"] == 200.00
    assert data["items"][1]["percent"] == pytest.approx(33.4, abs=0.1)
    # 前端要用 id 做「点扇区联动」
    assert data["items"][0]["id"] is not None


def test_category_pie_income(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    data = auth_client.get(
        f"/api/stats/category-pie?year={year}&month={month}&type=income"
    ).get_json()["data"]
    assert data["total"] == 1000.00
    assert data["items"][0]["name"] == "工资"


def test_monthly_trend(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    response = auth_client.get(f"/api/stats/monthly-trend?end_year={year}&end_month={month}")
    data = response.get_json()["data"]
    assert len(data["labels"]) == 6
    assert data["labels"][-1] == f"{year}-{month:02d}"
    assert data["expense"][-1] == 300.50
    assert data["income"][-1] == 1000.00
    # 上一个月（倒数第二个）应当有 50.25 的支出
    assert data["expense"][-2] == 50.25


def test_daily_trend_fills_zeros(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    data = auth_client.get(f"/api/stats/daily-trend?year={year}&month={month}").get_json()["data"]
    days = calendar.monthrange(year, month)[1]
    assert len(data["labels"]) == days
    assert len(data["expense"]) == days
    assert sum(data["expense"]) == pytest.approx(300.50)
    assert data["expense"][0] == 300.50


def test_daily_trend_no_data_month(auth_client):
    """无数据月份：全部补 0，不能出现 NaN / 长度不一致。"""
    data = auth_client.get("/api/stats/daily-trend?year=2020&month=1").get_json()["data"]
    assert len(data["labels"]) == 31
    assert set(data["expense"]) == {0.0}


def test_daily_trend_by_category(auth_client, demo, sample_records):
    category = category_by_name(demo.id, "交通")
    year, month = sample_records["year"], sample_records["month"]
    data = auth_client.get(
        f"/api/stats/daily-trend?year={year}&month={month}&category_id={category.id}"
    ).get_json()["data"]
    assert sum(data["expense"]) == pytest.approx(200.00)


def test_heatmap(auth_client, sample_records):
    year = sample_records["year"]
    data = auth_client.get(f"/api/stats/heatmap?year={year}").get_json()["data"]
    assert data["year"] == year
    assert data["max"] == 300.50
    dates = [item[0] for item in data["values"]]
    assert sample_records["first_day"].isoformat() in dates


def test_top_categories_limit(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    data = auth_client.get(
        f"/api/stats/top-categories?year={year}&month={month}&limit=1"
    ).get_json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "交通"


@pytest.mark.parametrize(
    "query",
    [
        "/api/stats/overview?year=abc",
        "/api/stats/overview?month=13",
        "/api/stats/overview?month=0",
        "/api/stats/category-pie?type=transfer",
        "/api/stats/top-categories?limit=abc",
        "/api/stats/monthly-trend?months=999",
        "/api/stats/daily-trend?category_id=abc",
    ],
)
def test_api_invalid_params_return_400(auth_client, query):
    response = auth_client.get(query)
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == 1
    assert payload["msg"]


def test_api_json_structure(auth_client):
    payload = auth_client.get("/api/stats/overview").get_json()
    assert payload["code"] == 0
    assert "data" in payload


# ---------------------------------------------------------------------------
# 预算（加分项）
# ---------------------------------------------------------------------------
def test_save_budget_and_usage(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    auth_client.post("/budgets/save", data={"year": year, "month": month, "amount": "1000"})
    budget = Budget.query.filter_by(year=year, month=month).first()
    assert budget is not None and float(budget.amount) == 1000.0

    data = auth_client.get(f"/api/stats/overview?year={year}&month={month}").get_json()["data"]
    # 支出 300.50 / 预算 1000 = 30.05% → 正常
    assert data["budget"]["usage"] == pytest.approx(30.1, abs=0.1)
    assert data["budget"]["level"] == "normal"
    assert data["budget"]["remain"] == pytest.approx(699.50)


def test_budget_warn_and_over_levels(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    # 预算 350 → 支出 300.5 / 350 = 85.9% → warn
    auth_client.post("/budgets/save", data={"year": year, "month": month, "amount": "350"})
    data = auth_client.get(f"/api/stats/overview?year={year}&month={month}").get_json()["data"]
    assert data["budget"]["level"] == "warn"

    # 预算 200 → 150.25% → over
    auth_client.post("/budgets/save", data={"year": year, "month": month, "amount": "200"})
    data = auth_client.get(f"/api/stats/overview?year={year}&month={month}").get_json()["data"]
    assert data["budget"]["level"] == "over"
    assert data["budget"]["remain"] < 0


def test_budget_save_invalid_amount(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    response = auth_client.post(
        "/budgets/save", data={"year": year, "month": month, "amount": "abc"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert Budget.query.count() == 0


def test_budget_remove(auth_client, sample_records):
    year, month = sample_records["year"], sample_records["month"]
    auth_client.post("/budgets/save", data={"year": year, "month": month, "amount": "500"})
    assert Budget.query.count() == 1
    auth_client.post("/budgets/save", data={"year": year, "month": month, "amount": "0"})
    assert Budget.query.count() == 0


def test_budget_page_ok(auth_client):
    assert auth_client.get("/budgets").status_code == 200


# ---------------------------------------------------------------------------
# Ajax 快速记账
# ---------------------------------------------------------------------------
def test_api_create_record(auth_client, demo):
    category = category_by_name(demo.id, "餐饮")
    response = auth_client.post(
        "/api/records",
        json={
            "amount": "18.80",
            "type": "expense",
            "category_id": category.id,
            "record_date": date.today().strftime("%Y-%m-%d"),
            "note": "Ajax 快速记账",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    assert payload["data"]["amount"] == 18.8
    assert Record.query.filter_by(note="Ajax 快速记账").count() == 1


def test_api_create_record_invalid(auth_client):
    response = auth_client.post(
        "/api/records",
        json={"amount": "-1", "type": "expense", "record_date": date.today().isoformat()},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == 1
    assert payload["field"] == "amount"
    assert Record.query.count() == 0


def test_api_create_record_requires_login(client):
    response = client.post("/api/records", json={"amount": "1", "type": "expense"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 分类 / 账户管理
# ---------------------------------------------------------------------------
def test_create_custom_category(auth_client, demo):
    response = auth_client.post(
        "/categories/create",
        data={"name": "宠物", "type": "expense", "icon": "🐱", "color": "#ff8800"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert category_by_name(demo.id, "宠物") is not None


def test_create_duplicate_category_rejected(auth_client, demo):
    response = auth_client.post(
        "/categories/create",
        data={"name": "餐饮", "type": "expense", "icon": "🍜", "color": "#f97316"},
    )
    assert response.status_code == 400
    assert "已存在" in response.get_data(as_text=True)


def test_default_category_cannot_be_deleted(auth_client, demo):
    category = category_by_name(demo.id, "餐饮")
    response = auth_client.post(f"/categories/{category.id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert db.session.get(type(category), category.id) is not None


def test_delete_custom_category_keeps_records(auth_client, demo):
    """删除自定义分类后，历史账目保留并变成「未分类」——这是 ON DELETE SET NULL 的效果。"""
    auth_client.post(
        "/categories/create",
        data={"name": "宠物", "type": "expense", "icon": "🐱", "color": "#ff8800"},
    )
    category = category_by_name(demo.id, "宠物")
    record = make_record(demo.id, "30.00", "expense", "宠物", date.today(), "猫粮")
    response = auth_client.post(f"/categories/{category.id}/delete", follow_redirects=True)
    assert response.status_code == 200
    kept = db.session.get(Record, record.id)
    assert kept is not None
    assert kept.category_id is None


def test_account_pages_and_crud(auth_client, demo):
    assert auth_client.get("/accounts").status_code == 200
    response = auth_client.post(
        "/accounts/create", data={"name": "校园卡", "kind": "bank"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert any(a.name == "校园卡" for a in demo.accounts)


def test_update_account_duplicate_name_rejected(auth_client, demo):
    """把账户改名成已存在的名字：必须给出友好提示，不能撞唯一约束变成 500。"""
    response = auth_client.post(
        "/accounts/create", data={"name": "校园卡", "kind": "bank"}, follow_redirects=True
    )
    assert response.status_code == 200
    account = next(a for a in demo.accounts if a.name == "校园卡")
    response = auth_client.post(
        f"/accounts/{account.id}/update",
        data={"name": "微信", "kind": "wechat"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "已存在同名账户" in response.get_data(as_text=True)
