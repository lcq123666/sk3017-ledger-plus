"""演示数据生成器（纯 Python，不依赖 Flask，可被 CLI / 测试 / SQL 生成脚本复用）。

为什么单独抽出来：
1. `flask --app run.py seed-demo` 用它往数据库里写演示数据；
2. `python database/seed_data.py` 用它生成等价的 `database/seed.sql`，
   这样「ORM 导入」和「纯 SQL 导入」两条路径的数据完全一致，不会出现两套口径；
3. 随机种子固定，任何人任何机器生成的演示数据（金额、备注、日期分布）都相同，便于核对截图。
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# 固定随机种子：保证演示数据可复现
RANDOM_SEED = 20261030
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123456"
DEMO_NICKNAME = "记账小能手"

# 演示数据的起止日期（覆盖 3 个完整自然月 + 半个月，满足"至少 3 个月、50 条以上"）
START_DATE = date(2026, 7, 15)
END_DATE = date(2026, 10, 30)


def _money(value: float) -> float:
    """金额统一保留两位小数，避免浮点误差带进数据库。"""
    return round(float(value), 2)


# ---------------------------------------------------------------------------
# 各类支出的金额区间与出现概率（模拟真实记账习惯：餐饮高频小额，居住低频大额）
# ---------------------------------------------------------------------------
_EXPENSE_RULES = [
    # (分类, 账户, 概率, 最小金额, 最大金额, 备注候选)
    ("餐饮", "微信", 1.00, 12, 68, ["食堂午饭", "外卖晚餐", "早餐豆浆油条", "和室友加餐", "周末火锅", "奶茶+小吃"]),
    ("交通", "支付宝", 0.45, 3, 26, ["地铁通勤", "共享单车", "公交", "打车回学校", "高铁票"]),
    ("学习", "支付宝", 0.16, 19, 220, ["买专业书", "打印复习资料", "网课会员", "四六级报名费", "实验耗材"]),
    ("娱乐", "微信", 0.20, 25, 180, ["看电影", "剧本杀", "switch 游戏", "演唱会门票", "剧本杂志"]),
    ("购物", "支付宝", 0.18, 39, 420, ["换季衣服", "洗发水等日用品", "数据线", "运动鞋", "键盘键帽"]),
    ("医疗", "现金", 0.04, 25, 200, ["感冒药", "校医院挂号", "眼药水", "牙科检查"]),
    ("其他支出", "现金", 0.05, 10, 120, ["打印店", "快递费", "办卡押金", "给室友垫付"]),
]


def build_demo_data() -> dict:
    """生成演示数据。

    返回：{"records": [...], "budgets": [...], "categories": [...], "accounts": [...]}
    record 字段：amount / type / category / account / record_date(date) / note
    """
    rng = random.Random(RANDOM_SEED)
    records = []

    def add(d: date, ctype: str, category: str, account: str, amount: float, note: str):
        records.append(
            {
                "record_date": d,
                "type": ctype,
                "category": category,
                "account": account,
                "amount": _money(amount),
                "note": note,
            }
        )

    day = START_DATE
    while day <= END_DATE:
        # 居住：每月 1 号交房租，5 号交水电
        if day.day == 1:
            add(day, "expense", "居住", "银行卡", 1500, "合租房租")
        if day.day == 5:
            add(day, "expense", "居住", "支付宝", rng.uniform(78, 165), "水电燃气费")

        # 日常支出：按概率生成
        for category, account, probability, low, high, notes in _EXPENSE_RULES:
            if rng.random() >= probability:
                continue
            times = 1
            if category == "餐饮":
                times = rng.choice([1, 2, 2, 3])
            for _ in range(times):
                add(day, "expense", category, account, rng.uniform(low, high), rng.choice(notes))

        # 收入：每月 10 号发工资；不定期兼职、红包、奖学金
        if day.day == 10:
            add(day, "income", "工资", "银行卡", 8500, "实习工资")
        if rng.random() < 0.06:
            add(day, "income", "兼职", "支付宝", rng.uniform(180, 1200), "外包小活结算")
        if rng.random() < 0.05:
            add(day, "income", "红包", "微信", rng.uniform(20, 200), "家里给的生活费")
        if day == date(2026, 9, 18):
            add(day, "income", "奖学金", "银行卡", 2000, "校级奖学金")

        day += timedelta(days=1)

    records.sort(key=lambda r: (r["record_date"], r["type"]))

    # 预算刻意做出三种状态：接近上限（warn）、已经超支（over）、留有余量（normal）
    budgets = [
        {"year": 2026, "month": 7, "amount": _money(3000)},
        {"year": 2026, "month": 8, "amount": _money(6500)},
        {"year": 2026, "month": 9, "amount": _money(8000)},
        {"year": 2026, "month": 10, "amount": _money(7000)},
    ]

    return {
        "records": records,
        "budgets": budgets,
        "username": DEMO_USERNAME,
        "password": DEMO_PASSWORD,
        "nickname": DEMO_NICKNAME,
    }


# ---------------------------------------------------------------------------
# 生成 database/seed.sql（供「纯 SQL 导入」路径使用）
# ---------------------------------------------------------------------------
def build_sql(password_hash: str) -> str:
    data = build_demo_data()
    lines = [
        "-- ---------------------------------------------------------------------------",
        "-- 个人记账本 演示数据（由 database/seed_data.py 自动生成，请勿手工修改）",
        f"-- 演示账号：{DEMO_USERNAME} / {DEMO_PASSWORD}",
        f"-- 数据范围：{START_DATE} ~ {END_DATE}，共 {len(data['records'])} 条记账记录",
        "-- ---------------------------------------------------------------------------",
        "SET NAMES utf8mb4;",
        "USE sk3017_ledger;",
        "",
        "-- 清空旧数据（按外键依赖顺序）",
        "DELETE FROM record;",
        "DELETE FROM budget;",
        "DELETE FROM `category`;",
        "DELETE FROM account;",
        "DELETE FROM `user`;",
        "ALTER TABLE record AUTO_INCREMENT = 1;",
        "ALTER TABLE budget AUTO_INCREMENT = 1;",
        "ALTER TABLE `category` AUTO_INCREMENT = 1;",
        "ALTER TABLE account AUTO_INCREMENT = 1;",
        "ALTER TABLE `user` AUTO_INCREMENT = 1;",
        "",
        "-- 用户",
        "INSERT INTO `user` (id, username, password_hash, nickname, email, created_at) VALUES",
        f"  (1, '{DEMO_USERNAME}', '{password_hash}', '{DEMO_NICKNAME}', 'demo@example.com', '2026-07-15 09:00:00');",
        "",
    ]

    # 分类：与 app/models.py 的 DEFAULT_CATEGORIES 保持一致
    from app.models import DEFAULT_CATEGORIES  # noqa: PLC0415  (脚本内延迟导入，避免循环)

    lines.append("-- 分类（系统预置 13 个）")
    lines.append("INSERT INTO `category` (user_id, name, type, icon, color, is_default, sort_order) VALUES")
    rows = [
        f"  (1, '{name}', '{ctype}', '{icon}', '{color}', 1, {order})"
        for name, ctype, icon, color, order in DEFAULT_CATEGORIES
    ]
    lines.append(",\n".join(rows) + ";")
    lines.append("")

    lines.append("-- 账户（默认 4 个）")
    lines.append("INSERT INTO account (user_id, name, kind) VALUES")
    lines.append("  (1, '现金', 'cash'),")
    lines.append("  (1, '支付宝', 'alipay'),")
    lines.append("  (1, '微信', 'wechat'),")
    lines.append("  (1, '银行卡', 'bank');")
    lines.append("")

    lines.append("-- 预算")
    lines.append("INSERT INTO budget (user_id, year, month, amount) VALUES")
    lines.append(
        ",\n".join(
            f"  (1, {b['year']}, {b['month']}, {b['amount']:.2f})" for b in data["budgets"]
        )
        + ";"
    )
    lines.append("")

    lines.append(f"-- 记账记录（{len(data['records'])} 条）")
    lines.append(
        "INSERT INTO record (user_id, amount, type, category_id, account_id, record_date, note) VALUES"
    )
    value_rows = []
    for rec in data["records"]:
        note = (rec["note"] or "").replace("'", "''")
        value_rows.append(
            "  (1, {amount:.2f}, '{type}', "
            "(SELECT id FROM `category` WHERE user_id=1 AND name='{category}' AND type='{type}'), "
            "(SELECT id FROM account WHERE user_id=1 AND name='{account}'), "
            "'{date}', '{note}')".format(
                amount=rec["amount"],
                type=rec["type"],
                category=rec["category"],
                account=rec["account"],
                date=rec["record_date"].strftime("%Y-%m-%d"),
                note=note,
            )
        )
    lines.append(",\n".join(value_rows) + ";")
    lines.append("")
    lines.append("-- 校验：应当分别为 1、13、4、4、N")
    lines.append("SELECT (SELECT COUNT(*) FROM `user`) AS users,")
    lines.append("       (SELECT COUNT(*) FROM `category`) AS categories,")
    lines.append("       (SELECT COUNT(*) FROM account) AS accounts,")
    lines.append("       (SELECT COUNT(*) FROM budget) AS budgets,")
    lines.append("       (SELECT COUNT(*) FROM record) AS records;")
    lines.append("")
    return "\n".join(lines)


def _main() -> int:
    from werkzeug.security import generate_password_hash

    # 直接执行 `python database/seed_data.py` 时，sys.path[0] 是 database/ 目录，
    # 这里把项目根目录加进搜索路径，才能 import 到 app 包。
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    password_hash = generate_password_hash(DEMO_PASSWORD, method="pbkdf2:sha256")
    sql = build_sql(password_hash)
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path(__file__).resolve().parent / "seed.sql"
    target.write_text(sql, encoding="utf-8")
    print(f"已生成 {target}（{len(sql.splitlines())} 行）")
    print(json.dumps({"records": len(build_demo_data()["records"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
