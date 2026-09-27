"""命令行工具：建表、导入演示数据、重置数据库。

用法（在项目根目录）：
    flask --app run.py init-db        # 建表
    flask --app run.py seed-demo      # 导入演示账号与 3 个月以上的记账数据
    flask --app run.py reset-db --yes # 删表重建并重新导入演示数据
"""
import click
from flask import Flask

from .extensions import db
from .models import Account, Budget, Category, Record, User
from .services import ensure_user_defaults

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123456"


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """按 models.py 建表（等价于执行 database/schema.sql）。"""
        db.create_all()
        click.secho("[OK] 数据表创建完成", fg="green")
        _print_tables()

    @app.cli.command("seed-demo")
    def seed_demo():
        """导入演示账号 demo/demo123456 与 3 个月以上的演示记账数据。"""
        from database.seed_data import DEMO_PASSWORD as SEED_PASSWORD
        from database.seed_data import build_demo_data

        db.create_all()
        user = User.query.filter_by(username=DEMO_USERNAME).first()
        if user is None:
            user = User(username=DEMO_USERNAME, nickname="记账小能手", email="demo@example.com")
            user.set_password(SEED_PASSWORD)
            db.session.add(user)
            db.session.flush()
            ensure_user_defaults(user)
            click.secho(f"[OK] 创建演示账号 {DEMO_USERNAME}", fg="green")
        else:
            ensure_user_defaults(user)
            click.secho(f"[i] 演示账号 {DEMO_USERNAME} 已存在，先清空原有演示数据", fg="yellow")
            Record.query.filter_by(user_id=user.id).delete()
            Budget.query.filter_by(user_id=user.id).delete()
            db.session.commit()

        categories = {c.name: c for c in Category.query.filter_by(user_id=user.id).all()}
        accounts = {a.name: a for a in Account.query.filter_by(user_id=user.id).all()}

        payload = build_demo_data()
        records = []
        for item in payload["records"]:
            category = categories.get(item["category"])
            account = accounts.get(item["account"])
            records.append(
                Record(
                    user_id=user.id,
                    amount=item["amount"],
                    type=item["type"],
                    category_id=category.id if category else None,
                    account_id=account.id if account else None,
                    record_date=item["record_date"],
                    note=item["note"],
                )
            )
        db.session.add_all(records)
        for item in payload["budgets"]:
            db.session.add(
                Budget(
                    user_id=user.id,
                    year=item["year"],
                    month=item["month"],
                    amount=item["amount"],
                )
            )
        db.session.commit()
        click.secho(
            f"[OK] 已导入 {len(records)} 条记账记录、{len(payload['budgets'])} 条预算",
            fg="green",
        )
        click.echo(f"  演示账号：{DEMO_USERNAME} / {SEED_PASSWORD}")

    @app.cli.command("reset-db")
    @click.option("--yes", is_flag=True, help="确认删除所有数据（必须显式指定）")
    def reset_db(yes: bool):
        """删表 → 重建 → 重新导入演示数据。"""
        if not yes:
            click.secho("[!] 该命令会删除全部数据，确认请加 --yes", fg="red")
            return
        db.drop_all()
        db.create_all()
        click.secho("[OK] 数据表已重建", fg="green")
        # 复用 seed-demo 逻辑
        from flask.cli import with_appcontext  # noqa: F401

        ctx = click.get_current_context()
        ctx.invoke(seed_demo)


def _print_tables() -> None:
    """打印当前库里的表名，方便确认连的是不是目标数据库。"""
    from sqlalchemy import inspect

    inspector = inspect(db.engine)
    names = ", ".join(inspector.get_table_names())
    click.echo(f"  当前数据库表：{names}")
