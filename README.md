课程设计选题：题目三-个人记账本（收支管理+图表统计）

# 轻记账 · 个人记账本 Web 应用

> SK3017《Python Web企业级项目开发》 ｜ 2026-2027 第一学期课程设计 ｜ 路线B（题库选题） ｜ 一人独立完成
> 技术栈：Python 3.12 / Flask 3.1 / MySQL 8.0 / Jinja2 / Bootstrap 5.3 / ECharts 5.5
> **代码仓库**：<https://github.com/lcq123666/sk3017-ledger-plus>（公开仓库，可直接访问）

一个自托管、轻量、带统计的个人记账本：注册登录后按"金额 + 类型 + 分类 + 账户 + 日期 + 备注"记录每一笔收支，通过年/月/类型/分类/关键词组合筛选快速定位流水，并在统计页用五张图表看清"钱花在哪儿、每月花多少、这个月比上个月多花了还是少花了"。

---

## 一、功能清单

### 1.1 基础必做功能

| 编号 | 功能 | 实现说明 |
| --- | --- | --- |
| F-01 | 用户注册 | 用户名 2~20 位中英文/数字/下划线且唯一；密码 6~64 位，`pbkdf2:sha256` 加盐哈希存储；注册时自动创建 13 个预置分类与 4 个默认账户 |
| F-02 | 用户登录 | Flask-Login 会话管理，支持"记住我"；登录失败统一提示"用户名或密码错误"，不泄露账号是否存在；`next` 跳转做站内校验防开放重定向 |
| F-03 | 退出登录 | 清理会话并回到登录页 |
| F-04 | 会话保护 | 未登录访问业务页面自动 302 到登录页；未登录调用 API 返回 401 JSON |
| F-05 | 记一笔（新增） | 金额、类型、日期必填，分类与账户可选；服务端二次校验 |
| F-06 | 编辑账目 | 复用记一笔表单并回填原值，修改后立即生效 |
| F-07 | 删除账目 | POST 提交 + 前端二次确认弹窗，删除后回到来源页并保留筛选条件 |
| F-08 | 流水查询 | 按日期倒序展示，支持年、月、类型、分类、关键词五个条件任意组合 |
| F-09 | 分页 | 每页固定 10 条；分页参数统一校验，非法值回落第 1 页而不是 500 |
| F-10 | 金额校验 | 正数、最多两位小数、上限 99999999.99，拒绝科学计数法与负数 |
| F-11 | 日期校验 | `YYYY-MM-DD` 格式，不早于 2000-01-01，不晚于今天 |
| F-12 | 统计图表（核心三图） | 分类占比饼图、近 6 个月收支并列柱状图、当月每日支出折线图；全部服务端 SQL 聚合，Ajax 随筛选联动刷新，空数据不白屏 |
| F-13 | 演示数据 | `seed-demo` 生成 demo 账号与 2026-07-15 ~ 2026-10-30 共 **365 条**记录、4 条月度预算 |

### 1.2 加分项功能（已实现）

| 编号 | 加分项 | 实现说明 |
| --- | --- | --- |
| B-01 | 月度预算 + 进度条 | 按月设置预算，使用率 ≥80% 黄色提醒、≥100% 红色超支警示；展示近 6 个月执行历史 |
| B-02 | 自定义分类管理 | 分类增删改，支持 Emoji 图标与颜色；系统预置分类不可删除但可改名改色 |
| B-03 | 资金账户管理 | 现金 / 支付宝 / 微信 / 银行卡四类账户增删改，至少保留一个账户 |
| B-04 | CSV 导出 | 按当前筛选条件导出，UTF-8 BOM 保证 Excel 打开中文不乱码，中文文件名按 RFC 5987 编码 |
| B-05 | 年度支出日历热力图 | 按日聚合全年支出，颜色深浅表示当天消费水平 |
| B-06 | 支出 TOP5 + 环比/同比 | 指标卡展示本月收入/支出/结余的环比（上月）与同比（去年同月），基期为 0 时显示"—" |
| B-07 | 首页 Ajax 快速记一笔 | 不刷新页面即可完成记账，成功后局部刷新概览与最近记录 |
| B-08 | 深浅色主题 + 响应式 | `data-bs-theme` 一键切换并记忆选择，首屏内联脚本防闪烁；1920 与 390 宽度下布局可用 |
| B-09 | 统一 JSON 错误结构 + 错误页 | 成功 `{"code":0,"msg":"ok","data":...}`，失败 `{"code":1,"msg":"...","field":"可选"}`；400/403/404/500 中文错误页 |
| B-10 | pytest 自动化测试 | 5 个测试文件、88 个测试函数，参数化展开后 **117 个用例**，覆盖正常、异常与边界，`pytest -q` 全部通过 |

### 1.3 项目指标

| 指标 | 数量 | 说明 |
| --- | --- | --- |
| 数据表 | 5 张 | user / account / category / record / budget |
| 页面 | 7 个 | 概览、流水、记一笔/编辑、统计、分类管理、账户管理、预算管理（另有登录/注册） |
| 统计接口 | 6 个 | 概览、分类占比、月度趋势、每日趋势、热力图、TOP N |
| 自动化测试 | 117 个 | `pytest -q` 全部通过（约 1 分钟） |
| 演示数据 | 365 条 | 2026-07-15 ~ 2026-10-30，另含 4 条月度预算 |
| 运行截图 | 12 张 | 位于 `screenshots/`，含深色主题与移动端 |
| 加分项 | 10 项 | 预算、分类/账户管理、CSV 导出、热力图、TOP5+环比同比、快速记账、主题响应式、统一错误、测试 |

---

## 二、技术栈

| 层次 | 技术 | 版本 | 用途 |
| --- | --- | --- | --- |
| 语言 | Python | 3.12 | 后端开发语言 |
| Web 框架 | Flask | 3.1.3 | 应用工厂、蓝图、路由 |
| ORM | Flask-SQLAlchemy | 3.1.1 | ORM 映射与聚合查询 |
| 认证 | Flask-Login | 0.6.3 | 会话管理与登录保护 |
| 表单安全 | Flask-WTF / WTForms | 1.3.0 / 3.3.1 | 全局 CSRF 防护 |
| 数据库 | MySQL | 8.0（utf8mb4） | 业务数据存储 |
| 驱动 | PyMySQL + cryptography | 1.2.3 / 50.0.2 | 连接 MySQL 8（caching_sha2_password） |
| 配置 | python-dotenv | 1.2.4 | 从 `.env` 注入密钥与数据库连接串 |
| 模板 | Jinja2 | Flask 内置 | 服务端渲染 |
| 前端 | Bootstrap | 5.3（本地 vendor） | 栅格、组件、深色主题变量 |
| 图表 | ECharts | 5.5（本地 vendor） | 饼图、柱状图、折线图、热力图、条形图 |
| 测试 | pytest | 9.2.0 | 自动化测试（内存 SQLite） |

> 前端依赖全部下载到 `app/static/vendor/`，**不使用 CDN**，断网也能完整演示。

---

## 三、系统架构

```mermaid
graph TD
    subgraph 表现层
        A1[Jinja2 模板<br/>12 个页面 + base 布局]
        A2[Bootstrap 5.3<br/>本地 vendor]
        A3[ECharts 5.5<br/>5 张统计图表]
        A4[app.js / records.js / stats.js<br/>Ajax + 主题切换]
    end
    subgraph 业务层
        B1[Flask 应用工厂<br/>create_app]
        B2[auth 蓝图<br/>注册/登录/退出]
        B3[ledger 蓝图<br/>CRUD/筛选/导出/分类/账户/预算]
        B4[stats 蓝图<br/>统计聚合接口]
        B5[services.py<br/>业务与聚合逻辑]
        B6[utils.py<br/>参数校验/CSV/日期区间]
        B7[errors 蓝图<br/>错误页 + 统一 JSON]
    end
    subgraph 数据层
        C1[Flask-SQLAlchemy ORM]
        C2[PyMySQL 驱动]
        C3[(MySQL 8.0<br/>sk3017_ledger<br/>utf8mb4)]
    end
    A1 --> B1
    A2 --> A1
    A3 --> A4
    A4 -->|fetch JSON| B4
    A4 -->|fetch JSON| B3
    B1 --> B2
    B1 --> B3
    B1 --> B4
    B1 --> B7
    B2 --> B6
    B3 --> B5
    B3 --> B6
    B4 --> B5
    B5 --> C1
    B2 --> C1
    C1 --> C2
    C2 --> C3
```

**分层说明**：表现层由服务端渲染页面骨架，只在需要无刷新的场景（快速记账、统计联动、主题切换）用原生 `fetch`；业务层按业务域拆蓝图，聚合与校验逻辑集中在 `services.py` / `utils.py`；数据层用 SQLAlchemy 映射 5 张表，统计一律下推为 SQL 聚合。详细设计见 [`docs/设计文档.md`](docs/设计文档.md)。

---

## 四、目录结构

```text
sk3017-ledger-plus/
├── app/
│   ├── __init__.py            # 应用工厂：扩展初始化、蓝图注册、错误处理、模板 global、CLI 注册、日志
│   ├── extensions.py          # db / login_manager / csrf 单例（避免循环导入）
│   ├── models.py              # 5 张表 ORM 模型 + 密码哈希 + 预置分类/账户常量
│   ├── services.py            # 业务逻辑：校验、聚合、趋势、预算、概览、列表查询
│   ├── utils.py               # 参数校验、日期区间、金额格式化、CSV 构造
│   ├── errors.py              # 错误页蓝图（/csrf-error、/healthz）
│   ├── cli.py                 # init-db / seed-demo / reset-db 命令
│   ├── auth/                  # 认证蓝图（注册/登录/退出）
│   ├── ledger/                # 记账蓝图（概览/流水/CRUD/分类/账户/预算/导出）
│   ├── stats/                 # 统计蓝图（页面 + 6 个 JSON 接口 + 快速记账）
│   ├── templates/             # base.html + auth(2) + ledger(5) + stats(1) + errors(4)
│   └── static/
│       ├── css/app.css        # 自定义样式与主题变量
│       ├── js/                # app.js / records.js / stats.js
│       └── vendor/            # bootstrap.min.css、bootstrap.bundle.min.js、echarts.min.js
├── config.py                  # 配置类（开发/测试），从 .env 注入
├── run.py                     # 应用入口，默认 http://127.0.0.1:5001
├── requirements.txt           # 锁定版本的依赖清单
├── .env.example               # 环境变量示例（复制为 .env 使用）
├── .gitignore
├── database/
│   ├── schema.sql             # 建库 + 5 张表 + 索引 + 外键（MySQL 8 / utf8mb4）
│   ├── seed_data.py           # 演示数据生成器（固定随机种子，可生成 seed.sql）
│   └── seed.sql               # 由 seed_data.py 生成的等价 SQL 导入脚本
├── docs/
│   ├── 设计文档.md            # 需求、架构、数据库、核心流程、聚合 SQL、技术决策
│   ├── 接口文档.md            # 全部接口、参数、响应、错误码、curl 示例
│   ├── AI协作记录.md          # 8 个协作场景的意图/提示词/回复摘要/我的修改
│   ├── DEVELOPMENT_LOG.md     # 里程碑总览 + 09-21 ~ 10-30 按日开发记录
│   └── DEBUG_LOG.md           # 12 个真实问题的现象/根因/解决/预防 + 复盘
├── tests/
│   ├── conftest.py            # app / client / demo / login / sample_records 夹具
│   ├── test_validation.py     # 校验函数与日期工具（单元测试）
│   ├── test_auth.py           # 注册、登录、会话、开放重定向、密码哈希
│   ├── test_records.py        # CRUD、筛选、分页、越权、CSV 导出
│   ├── test_stats.py          # 概览、五类图表、预算、分类与账户管理、Ajax 接口
│   └── test_pages.py          # 页面渲染冒烟、健康检查、静态资源 MIME、导出响应头
├── screenshots/               # 12 张运行截图（登录、概览、流水、统计、深色、移动端等）
└── logs/                      # 运行日志（自动生成，已 gitignore）
```

---

## 五、快速开始

### 5.1 环境要求

- Python 3.12（3.10+ 均可运行）
- MySQL 8.0（字符集 utf8mb4）
- Windows / macOS / Linux 均可

### 5.2 第一步：创建数据库

MySQL 8.0 默认认证插件是 `caching_sha2_password`，连接需要 `cryptography`（已在 `requirements.txt` 中）。

```sql
CREATE DATABASE sk3017_ledger
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

也可以直接用建表脚本一次完成建库、建表、建索引：

```bash
mysql -uroot -p < database/schema.sql
```

### 5.3 第二步：创建虚拟环境

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

### 5.4 第三步：安装依赖

```bash
pip install -r requirements.txt
```

### 5.5 第四步：配置环境变量

```bash
# Windows PowerShell
Copy-Item .env.example .env
# macOS / Linux
cp .env.example .env
```

编辑 `.env`，把 `SECRET_KEY` 换成随机字符串、`DATABASE_URL` 里的用户名和口令换成本机 MySQL 的真实值：

```dotenv
SECRET_KEY=换成你自己的随机密钥
DATABASE_URL=mysql+pymysql://root:你的数据库口令@127.0.0.1:3306/sk3017_ledger?charset=utf8mb4
```

> `.env` 已被 `.gitignore` 忽略，不会提交到仓库。

### 5.6 第五~七步：建表、导入演示数据、启动

```bash
# ⑤ 按 ORM 模型建表（也可以跳过，改用 5.2 的 schema.sql）
flask --app run.py init-db
# ⑥ 导入演示账号与演示数据
flask --app run.py seed-demo
# ⑦ 启动开发服务器
python run.py
```

浏览器打开 <http://127.0.0.1:5001>，使用演示账号登录：

| 用户名 | 密码 | 说明 |
| --- | --- | --- |
| `demo` | `demo123456` | 已导入 365 条记录（2026-07-15 ~ 2026-10-30）与 4 条月度预算；10 月预算使用率约 97%（黄色预警）、8 月约 116.2%（红色超支），可直接演示预算的三种状态 |

### 5.7 第八步：运行测试

```bash
pytest -q
```

测试使用内存 SQLite，不依赖本机 MySQL，可在任何机器上直接跑；预期输出 `117 passed`（约 1 分钟）。

### 5.8 纯 SQL 导入演示数据（可选）

如果不想用 CLI 的 ORM 导入，可以执行生成的 SQL（**需先执行 `schema.sql` 建表**，`seed.sql` 内含 `USE sk3017_ledger;`）：

```bash
mysql -uroot -p < database/schema.sql
mysql -uroot -p < database/seed.sql
```

`database/seed.sql` 由 `database/seed_data.py` 生成，两者数据完全一致：

```bash
python database/seed_data.py database/seed.sql
```

### 5.9 其他 CLI 命令

| 命令 | 作用 |
| --- | --- |
| `flask --app run.py init-db` | 按 `models.py` 建表，输出 `[OK] 数据表创建完成` 并列出表名 |
| `flask --app run.py seed-demo` | 导入/刷新演示账号与 365 条记录、4 条预算 |
| `flask --app run.py reset-db --yes` | 删表重建并重新导入演示数据（会清空全部数据，必须显式加 `--yes`） |

健康检查：`GET http://127.0.0.1:5001/healthz` 返回 `{"status":"ok","db":"up"}`。

---

## 六、接口速查表

完整参数与示例见 [`docs/接口文档.md`](docs/接口文档.md)。

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/` | 登录 | 概览首页：本月收支、环比同比、预算、最近记录、快速记账 |
| GET | `/records` | 登录 | 流水列表：`year/month/type/category_id/keyword/page` |
| GET/POST | `/records/create` | 登录 | 记一笔（表单） |
| GET/POST | `/records/<rid>/edit` | 登录 | 编辑记录 |
| POST | `/records/<rid>/delete` | 登录 + CSRF | 删除记录 |
| GET | `/export.csv` | 登录 | 按筛选条件导出 CSV（UTF-8 BOM） |
| GET | `/categories` | 登录 | 分类管理页 |
| POST | `/categories/create` | 登录 + CSRF | 新增分类 |
| POST | `/categories/<cid>/update` | 登录 + CSRF | 修改分类 |
| POST | `/categories/<cid>/delete` | 登录 + CSRF | 删除自定义分类 |
| GET | `/accounts` | 登录 | 账户管理页 |
| POST | `/accounts/create` | 登录 + CSRF | 新增账户 |
| POST | `/accounts/<aid>/update` | 登录 + CSRF | 修改账户 |
| POST | `/accounts/<aid>/delete` | 登录 + CSRF | 删除账户 |
| GET | `/budgets` | 登录 | 预算页（当月 + 近 6 个月历史） |
| POST | `/budgets/save` | 登录 + CSRF | 保存/取消月度预算 |
| GET | `/stats` | 登录 | 统计页（4 张指标卡 + 5 张图表） |
| GET | `/api/stats/overview` | 登录 | 概览指标：`year/month` |
| GET | `/api/stats/category-pie` | 登录 | 分类占比饼图：`year/month/type` |
| GET | `/api/stats/monthly-trend` | 登录 | 近 N 个月收支：`end_year/end_month/months` |
| GET | `/api/stats/daily-trend` | 登录 | 当月每日收支：`year/month/category_id` |
| GET | `/api/stats/heatmap` | 登录 | 年度支出热力图：`year` |
| GET | `/api/stats/top-categories` | 登录 | 支出 TOP N：`year/month/type/limit` |
| POST | `/api/records` | 登录 + CSRF | Ajax 快速记一笔（JSON） |
| GET | `/login`、`/register`、`/logout` | - / 登录 | 认证页面 |
| GET | `/healthz` | 无 | 健康检查 |
| GET | `/csrf-error` | 无 | CSRF 失败提示页/JSON |

成功响应统一为 `{"code":0,"msg":"ok","data":...}`，失败为 `{"code":1,"msg":"...","field":"可选"}`；未登录调用 API 返回 `401` JSON，而不是重定向到登录页。

---

## 七、项目结构说明

- **`app/__init__.py`**：应用工厂 `create_app(config_name)`。按"扩展初始化 → 蓝图注册 → 模板过滤器与 global → 错误处理 → CLI → 日志"的顺序装配，支持测试注入不同配置。
- **`app/models.py`**：`user / account / category / record / budget` 五张表。金额用 `DECIMAL(10,2)`；`record` 建 `(user_id, record_date)` 与 `(user_id, category_id)` 复合索引；分类被删时记录保留、`category_id` 置空。
- **`app/services.py`**：所有聚合与业务口径的集中地（`period_totals`、`category_pie`、`monthly_trend`、`daily_trend`、`heatmap`、`top_categories`、`overview`、`budget_status`、`build_record_query`），页面与 JSON 接口复用同一份逻辑。
- **`app/utils.py`**：`parse_amount / parse_date / parse_int / parse_note / parse_type` 等校验函数、`month_range / shift_month / months_back` 日期工具、`fmt_money` 格式化、`build_records_csv` 导出。
- **`app/errors.py`**：CSRF 失败提示与健康检查。
- **`tests/`**：pytest 夹具集中在 `conftest.py`，每个测试函数一个全新内存库。

---

## 八、常见问题（FAQ）

### Q1：中文显示乱码 / 提示 `Incorrect string value`

建库与连接都必须使用 utf8mb4：

```sql
CREATE DATABASE sk3017_ledger DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

并在 `DATABASE_URL` 末尾带上 `?charset=utf8mb4`。如果已经建过库，用 `database/schema.sql` 重建（注意会删表）。

### Q2：导出的 CSV 用 Excel 打开中文乱码

项目导出时已写入 UTF-8 BOM，正常双击即可正确显示。若个别 Excel 版本仍乱码，用「数据 → 从文本/CSV 导入」，编码选 `UTF-8`（或 65001）。不要用记事本另存为 ANSI，会重新引入乱码。

### Q3：端口 5001 被占用

```bash
# 查看占用进程
netstat -ano | findstr :5001
# 临时换端口启动
set FLASK_RUN_PORT=5002 && python run.py     # Windows cmd
$env:FLASK_RUN_PORT=5002; python run.py      # PowerShell
```

### Q4：MySQL 8 报 `cryptography is required for sha256_password or caching_sha2_password`

MySQL 8 默认认证插件是 `caching_sha2_password`，PyMySQL 需要 `cryptography` 才能完成认证。`pip install -r requirements.txt` 已包含该依赖；若手动安装过 PyMySQL，请补装：

```bash
pip install cryptography
```

### Q5：Windows 控制台报 `UnicodeEncodeError: 'gbk' codec can't encode character`

Windows GBK 控制台无法输出 `✔`、emoji 等字符。项目 CLI 输出已统一改用 ASCII 标记（`[OK]`、`[!]`、`[i]`）；如果自己的脚本还需要输出中文，可临时设置：

```bash
set PYTHONUTF8=1        # Windows cmd
$env:PYTHONUTF8=1       # PowerShell
chcp 65001              # 切换控制台为 UTF-8
```

### Q6：`flask --app run.py` 提示找不到命令

确认虚拟环境已激活、依赖已安装；也可以使用等价入口：

```bash
python -m flask --app run.py init-db
```

Windows 下若直接运行 `python -m flask.__main__` 会报 `No module named flask.__main__`，应使用上面的 `python -m flask` 形式。

---

## 九、演示截图

运行截图位于 `screenshots/`，均来自真实运行环境（`python run.py` + 演示账号登录）：

| 文件 | 内容 |
| --- | --- |
| `01_login.png` | 登录页（测试账号提示、表单校验） |
| `02_dashboard.png` | 概览首页（本月收支、环比同比、预算进度、最近记录、快速记账） |
| `03_records.png` | 流水列表（组合筛选、分页、导出入口、删除确认） |
| `04_record_form.png` | 记一笔表单（金额/分类/账户/日期/备注校验） |
| `05_stats.png` | 统计页（4 张指标卡 + 5 张图表联动） |
| `06_stats_dark.png` | 统计页深色主题 |
| `07_budget.png` | 预算管理（当月执行情况 + 近 6 个月历史） |
| `08_categories.png` | 分类管理（图标、颜色、预置分类保护） |
| `09_accounts.png` | 账户管理（现金/支付宝/微信/银行卡） |
| `10_dashboard_dark.png` | 概览首页深色主题 |
| `11_mobile_dashboard.png` | 移动端概览（390px 宽度） |
| `12_mobile_stats.png` | 移动端统计页（窄屏图表自适应） |

---

## 十、文档索引

| 文档 | 内容 |
| --- | --- |
| [`docs/SK3017课程设计报告（个人记账本）.pdf`](docs/SK3017课程设计报告（个人记账本）.pdf) | 课程设计报告（PDF，31 页；Word 源文件同目录 `.docx`），含架构图、ER 图、5 张表结构、核心功能代码与 12 张运行截图、结果分析与总结、仓库链接与 AI 协作说明 |
| [`docs/设计文档.md`](docs/设计文档.md) | 需求分析、三层架构、ER 图与表结构、三个核心流程、聚合 SQL 与索引分析、关键技术决策与权衡、安全清单、测试策略、已知不足 |
| [`docs/接口文档.md`](docs/接口文档.md) | 全部页面与 JSON 接口、统一响应结构、错误码表、CSRF 用法、curl 联调示例 |
| [`docs/AI协作记录.md`](docs/AI协作记录.md) | 8 个协作场景的意图 / 提示词 / AI 回复摘要 / 我的修改与采纳，以及 AI 使用原则与协作复盘 |
| [`docs/DEVELOPMENT_LOG.md`](docs/DEVELOPMENT_LOG.md) | M0~M6 里程碑总览 + 2026-09-21 ~ 2026-10-30 按日开发记录 |
| [`docs/DEBUG_LOG.md`](docs/DEBUG_LOG.md) | 17 个真实问题的现象 / 根因 / 解决 / 预防，以及分类复盘与改进计划 |

---

## 十一、说明

- **代码仓库**：<https://github.com/lcq123666/sk3017-ledger-plus>（仓库保持公开，便于评阅访问）。
- 本项目为课程设计个人独立完成，选题来自课程题库路线 B。
- 前端依赖已本地化（Bootstrap / ECharts 均位于 `app/static/vendor/`），不依赖外网 CDN。
- 演示数据由固定随机种子生成，任何机器上导入结果一致，便于复现截图与验收。
