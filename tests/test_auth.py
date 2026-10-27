"""认证模块测试：注册、登录、退出、未登录拦截、开放重定向。"""
from app.extensions import db
from app.models import User
from tests.conftest import PASSWORD


def test_register_page_ok(client):
    response = client.get("/register")
    assert response.status_code == 200


def test_register_success_creates_defaults(client, app):
    response = client.post(
        "/register",
        data={
            "username": "xiaoming",
            "nickname": "小明",
            "password": "abc123456",
            "confirm_password": "abc123456",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    user = User.query.filter_by(username="xiaoming").first()
    assert user is not None
    assert user.check_password("abc123456")
    # 注册时自动预置 13 个分类 + 4 个账户
    assert len(user.categories) == 13
    assert len(user.accounts) == 4


def test_register_duplicate_username(client):
    response = client.post(
        "/register",
        data={
            "username": "demo",
            "password": "abc123456",
            "confirm_password": "abc123456",
        },
    )
    assert response.status_code == 200
    assert "已被注册" in response.get_data(as_text=True)


def test_register_password_mismatch(client):
    response = client.post(
        "/register",
        data={
            "username": "xiaohong",
            "password": "abc123456",
            "confirm_password": "different",
        },
    )
    assert "不一致" in response.get_data(as_text=True)
    assert User.query.filter_by(username="xiaohong").first() is None


def test_register_short_password(client):
    response = client.post(
        "/register",
        data={"username": "xiaogang", "password": "123", "confirm_password": "123"},
    )
    assert "密码至少 6 位" in response.get_data(as_text=True)


def test_login_success(client, login):
    response = login()
    assert response.status_code == 200
    # 登录后首页可以访问
    assert client.get("/").status_code == 200


def test_login_wrong_password(client):
    response = client.post(
        "/login", data={"username": "demo", "password": "wrong-password"}, follow_redirects=True
    )
    assert "用户名或密码错误" in response.get_data(as_text=True)
    # 未登录访问首页仍会被拦截
    assert client.get("/").status_code == 302


def test_login_unknown_user_same_message(client):
    response = client.post(
        "/login", data={"username": "nobody", "password": "123456"}, follow_redirects=True
    )
    assert "用户名或密码错误" in response.get_data(as_text=True)


def test_protected_page_redirects_to_login(client):
    response = client.get("/records")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_api_unauthorized_returns_json_401(client):
    response = client.get("/api/stats/overview")
    assert response.status_code == 401
    payload = response.get_json()
    assert payload["code"] == 1
    assert "登录" in payload["msg"]


def test_logout(client, login):
    login()
    assert client.get("/").status_code == 200
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert client.get("/").status_code == 302


def test_open_redirect_blocked(client):
    """next 参数只能是站内路径，防止被当成钓鱼跳板。"""
    response = client.post(
        "/login?next=http://evil.example.com",
        data={"username": "demo", "password": PASSWORD},
    )
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]


def test_internal_next_allowed(client):
    response = client.post(
        "/login?next=/stats", data={"username": "demo", "password": PASSWORD}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/stats")


def test_password_is_hashed(app, demo):
    """任何情况下都不能把明文密码存进数据库。"""
    assert demo.password_hash != PASSWORD
    assert demo.password_hash.startswith("pbkdf2:sha256")
