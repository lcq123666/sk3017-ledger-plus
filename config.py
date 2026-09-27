"""项目配置模块。

所有可变配置都通过环境变量（.env 文件）注入，代码中不出现任何真实口令，
便于多环境切换，也避免把数据库密码提交到 Git 仓库。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# 读取项目根目录下的 .env（若不存在则静默跳过，使用下面的默认值）
load_dotenv(BASE_DIR / ".env")


class Config:
    """开发环境默认配置。"""

    # Flask 会话签名密钥：生产环境必须通过环境变量覆盖
    SECRET_KEY = os.getenv("SECRET_KEY", "sk3017-ledger-dev-secret-please-change")

    # 数据库连接串：默认 MySQL 8.0 + PyMySQL 驱动
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:root@127.0.0.1:3306/sk3017_ledger?charset=utf8mb4",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 连接池：pre_ping 防止 MySQL 8 小时空闲断连导致的 "MySQL server has gone away"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # 分页大小
    RECORDS_PER_PAGE = 10
    # 请求体上限（本项目只提交文本表单，限制 2MB 防御超大请求）
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    # CSRF 令牌有效期设为 None（随会话生命周期），避免统计页停留过久提交失败
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_FAILURE_VIEW = "errors.csrf_error"

    # 主题默认值
    DEFAULT_THEME = "light"


class TestConfig(Config):
    """自动化测试配置：使用内存 SQLite，测试之间互不污染。"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret"


CONFIG_MAP = {
    "default": Config,
    "development": Config,
    "testing": TestConfig,
}
