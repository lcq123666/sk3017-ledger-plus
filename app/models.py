"""数据模型（ORM）。

五张核心表：
    user      用户
    account   资金账户（现金 / 支付宝 / 微信 / 银行卡）
    category  收支分类（系统预置 + 用户自定义）
    record    记账条目（核心业务表）
    budget    月度预算

设计要点：
1. 金额统一用 DECIMAL(10, 2) 存储，避免 float 的二进制误差（0.1 + 0.2 != 0.3）；
2. record 表上建 (user_id, record_date) 复合索引，所有统计查询都按"用户 + 日期区间"过滤，
   这样在日期列上不做函数运算（如 YEAR(record_date)），索引才不会失效；
3. 分类/账户对用户做级联删除，但 record 的分类被删除时置空（SET NULL），
   保证历史账目不会因为"删了一个分类"而丢失。
"""
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    """用户表。密码只存哈希，永不存明文。"""

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(32), unique=True, nullable=False, comment="登录名")
    password_hash = db.Column(db.String(255), nullable=False, comment="密码哈希")
    nickname = db.Column(db.String(32), nullable=False, default="记账小能手")
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    accounts = db.relationship(
        "Account", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    categories = db.relationship(
        "Category", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    # ---- 密码相关 -------------------------------------------------
    def set_password(self, raw_password: str) -> None:
        """加盐哈希后保存，绝不落库明文。"""
        self.password_hash = generate_password_hash(raw_password, method="pbkdf2:sha256")

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<User {self.username}>"


class Account(db.Model):
    """资金账户：一笔账挂在哪个钱包上。"""

    __tablename__ = "account"
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_account_user_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(32), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default="cash", comment="账户类型")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user = db.relationship("User", back_populates="accounts")
    records = db.relationship("Record", back_populates="account")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Account {self.name}>"


class Category(db.Model):
    """收支分类。is_default=True 为系统预置分类，用户不可删除。"""

    __tablename__ = "category"
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", "type", name="uq_category_user_name_type"),
        db.Index("ix_category_user_type", "user_id", "type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(20), nullable=False)
    type = db.Column(db.String(8), nullable=False, default="expense", comment="expense/income")
    icon = db.Column(db.String(16), nullable=False, default="💰")
    color = db.Column(db.String(16), nullable=False, default="#6366f1")
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    user = db.relationship("User", back_populates="categories")
    records = db.relationship("Record", back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name}>"


class Record(db.Model):
    """记账条目（一条收入或一条支出）。"""

    __tablename__ = "record"
    __table_args__ = (
        # 统计与列表查询都走 "user_id + 日期区间"，复合索引覆盖该模式
        db.Index("ix_record_user_date", "user_id", "record_date"),
        db.Index("ix_record_user_category", "user_id", "category_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False, comment="金额，正数")
    type = db.Column(db.String(8), nullable=False, default="expense")
    category_id = db.Column(
        db.Integer, db.ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    account_id = db.Column(
        db.Integer, db.ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    record_date = db.Column(db.Date, nullable=False, index=True)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    user = db.relationship("User")
    category = db.relationship("Category", back_populates="records")
    account = db.relationship("Account", back_populates="records")

    @property
    def signed_amount(self) -> float:
        """带符号金额，方便前端直接展示 + / -。"""
        value = float(self.amount)
        return value if self.type == "income" else -value

    def to_dict(self) -> dict:
        """序列化：Ajax 快速记账接口与导出共用。"""
        return {
            "id": self.id,
            "amount": float(self.amount),
            "type": self.type,
            "type_label": "收入" if self.type == "income" else "支出",
            "category": self.category.name if self.category else "未分类",
            "category_color": self.category.color if self.category else "#94a3b8",
            "account": self.account.name if self.account else "-",
            "record_date": self.record_date.isoformat(),
            "note": self.note or "",
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Record {self.record_date} {self.type} {self.amount}>"


class Budget(db.Model):
    """月度预算：同一用户同一年月只有一条（数据库唯一约束兜底）。"""

    __tablename__ = "budget"
    __table_args__ = (
        db.UniqueConstraint("user_id", "year", "month", name="uq_budget_user_month"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Budget {self.year}-{self.month:02d} {self.amount}>"


# ---------------------------------------------------------------------------
# 系统预置分类：注册时自动为该用户复制一份，保证开箱即用
# 元组格式：(名称, 类型, 图标, 颜色, 排序)
# ---------------------------------------------------------------------------
DEFAULT_CATEGORIES = [
    # 支出
    ("餐饮", "expense", "🍜", "#f97316", 1),
    ("交通", "expense", "🚌", "#0ea5e9", 2),
    ("学习", "expense", "📚", "#8b5cf6", 3),
    ("娱乐", "expense", "🎮", "#ec4899", 4),
    ("购物", "expense", "🛒", "#14b8a6", 5),
    ("居住", "expense", "🏠", "#eab308", 6),
    ("医疗", "expense", "💊", "#ef4444", 7),
    ("其他支出", "expense", "🧾", "#94a3b8", 8),
    # 收入
    ("工资", "income", "💼", "#22c55e", 1),
    ("兼职", "income", "🧑‍💻", "#10b981", 2),
    ("奖学金", "income", "🏅", "#84cc16", 3),
    ("红包", "income", "🧧", "#f43f5e", 4),
    ("其他收入", "income", "💵", "#64748b", 5),
]

DEFAULT_ACCOUNTS = [
    ("现金", "cash"),
    ("支付宝", "alipay"),
    ("微信", "wechat"),
    ("银行卡", "bank"),
]
