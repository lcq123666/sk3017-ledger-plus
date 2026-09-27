"""Flask 扩展单例。

单独成模块，避免 app 工厂与模型之间循环导入（models 需要 db，工厂也需要 db）。
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# 未登录访问受保护页面时跳转的登录视图（蓝图名.视图名）
login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录后再继续操作。"
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"
