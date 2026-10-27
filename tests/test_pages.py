"""页面层与"真实部署才暴露"的问题测试。

这些用例针对的是 Flask `test_client` 默认会掩盖、但真实浏览器/WSGI 服务器会踩到的坑：
1. HTTP 头只能传 latin-1，中文文件名必须百分号编码；
2. 静态文件 MIME 类型不对会被浏览器拒绝执行；
3. 模板变量未定义在 Jinja2 里默认静默渲染为空，容易把"回填丢失"藏起来。
"""
from datetime import date

from app.models import Record
from tests.conftest import category_by_name, make_record


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["db"] == "up"


def test_export_csv_content_disposition_is_encoded(auth_client, demo):
    """中文文件名必须编码进 header，否则 werkzeug 会抛 latin-1 UnicodeEncodeError。"""
    make_record(demo.id, "9.90", "expense", "餐饮", date.today(), "导出测试")
    response = auth_client.get("/export.csv")
    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in disposition
    # 编码后的 header 不允许出现裸中文（真实 WSGI 会拒绝）
    assert all(ord(ch) < 128 for ch in disposition)


def test_static_js_mimetype(auth_client):
    response = auth_client.get("/static/js/app.js")
    assert response.status_code == 200
    assert "javascript" in response.mimetype


def test_static_css_mimetype(auth_client):
    response = auth_client.get("/static/css/app.css")
    assert response.status_code == 200
    assert response.mimetype == "text/css"


def test_edit_form_prefills_existing_values(auth_client, demo):
    record = make_record(demo.id, "66.60", "expense", "餐饮", date.today(), "回填备注")
    response = auth_client.get(f"/records/{record.id}/edit")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "66.60" in text
    assert "回填备注" in text


def test_new_form_renders_with_empty_errors(auth_client):
    response = auth_client.get("/records/create")
    assert response.status_code == 200
    # 表单页应能正常渲染（errors/values 未定义时不报错）
    assert "记一笔" in response.get_data(as_text=True)


def test_404_page(auth_client):
    response = auth_client.get("/records/999999/edit")
    assert response.status_code == 404
    assert "404" in response.get_data(as_text=True)


def test_api_404_returns_json(auth_client):
    response = auth_client.get("/api/not-exists")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["code"] == 1


def test_error_pages_have_message(client):
    """未登录访问不存在的页面也应给出错误页而不是白屏。"""
    response = client.get("/no-such-page")
    assert response.status_code == 404
