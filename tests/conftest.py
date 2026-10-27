"""pytest 公共夹具。

测试统一使用内存 SQLite（config.TestConfig）：
- 不依赖本机 MySQL，`pytest -q` 在任何机器上都能跑；
- 每个测试函数一个全新的空库，测试之间互不影响；
- 生产代码用的 MySQL 特有约束（utf8mb4、ON DELETE SET NULL）在 SQLite 下
  由 SQLAlchemy 的 ORM 行为兜底，因此用例重点是**业务规则**而不是 DDL 细节。
"""
from datetime import date, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import Account, Budget, Category, Record, User
from app.services import ensure_user_defaults

PASSWORD = "demo123456"


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        demo = User(username="demo", nickname="演示用户")
        demo.set_password(PASSWORD)
        db.session.add(demo)
        db.session.flush()
        ensure_user_defaults(demo)
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def demo(app):
    return User.query.filter_by(username="demo").first()


@pytest.fixture
def login(client):
    def _login(username="demo", password=PASSWORD):
        return client.post(
            "/login", data={"username": username, "password": password}, follow_redirects=True
        )

    return _login


@pytest.fixture
def auth_client(client, login):
    login()
    return client


def category_by_name(user_id: int, name: str) -> Category:
    return Category.query.filter_by(user_id=user_id, name=name).first()


def account_by_name(user_id: int, name: str) -> Account:
    return Account.query.filter_by(user_id=user_id, name=name).first()


def make_record(
    user_id: int,
    amount: str,
    ctype: str,
    category_name: str,
    day: date,
    note: str = "",
    account_name: str = "微信",
) -> Record:
    category = category_by_name(user_id, category_name)
    account = account_by_name(user_id, account_name)
    record = Record(
        user_id=user_id,
        amount=amount,
        type=ctype,
        category_id=category.id if category else None,
        account_id=account.id if account else None,
        record_date=day,
        note=note,
    )
    db.session.add(record)
    db.session.commit()
    return record


@pytest.fixture
def current_month():
    today = date.today()
    return today.year, today.month


@pytest.fixture
def sample_records(app, demo, current_month):
    """构造一组金额确定的样本数据（日期基于"今天"动态计算，任何时间跑都成立）。

    本月：餐饮 100.50 + 交通 200.00（支出 300.50）、工资 1000.00（收入）
    上月：餐饮 50.25（用于验证环比）
    """
    year, month = current_month
    first_day = date(year, month, 1)
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    prev_day = date(prev_year, prev_month, min(15, 28))
    # 上月日期肯定在今天之前；本月 1 号同理
    make_record(demo.id, "100.50", "expense", "餐饮", first_day, "食堂午饭")
    make_record(demo.id, "200.00", "expense", "交通", first_day, "高铁票")
    make_record(demo.id, "1000.00", "income", "工资", first_day, "实习补贴")
    make_record(demo.id, "50.25", "expense", "餐饮", prev_day, "上月聚餐")
    return {"year": year, "month": month, "first_day": first_day, "prev_day": prev_day}
