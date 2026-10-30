# 开发调试日志（DEBUG_LOG）

> 记录开发过程中真实出现并修复的 17 个问题。每条包含 **现象 / 根因 / 解决 / 预防** 四部分；日期与实际开发进度一致，编号在 `DEVELOPMENT_LOG.md` 中引用。
> 环境：Windows 11 + Python 3.12 + Flask 3.1 + MySQL 8.0（utf8mb4）+ Chrome/Edge。

---

## BUG-001 ｜ 09-25 ｜ 数据库中文明文正常，页面上中文备注显示成问号

**现象**：建库建表后录入一条备注为"和室友吃火锅"的记录，MySQL 命令行里 `SELECT` 出来是正常中文，但流水列表页显示为 `????`；再往数据库插入时偶尔报 `Incorrect string value: '\xE5\x92\x8C...' for column 'note'`。

**根因**：建库语句用的是 `CREATE DATABASE sk3017_ledger;`，没有显式指定字符集，MySQL 8.0 在部分 Windows 安装下默认字符集是 `utf8mb4`，但**连接层**的 `character_set_client / character_set_results` 是 `utf8mb3` 或 `latin1`；PyMySQL 连接串若没写 `charset`，会按服务端默认字符集协商，导致"表是 utf8mb4、连接是 utf8mb3/GBK"的混搭。插入 4 字节 emoji（分类图标）时直接报错，因为 utf8mb3 最多 3 字节。

**解决**：

```sql
-- database/schema.sql 开头强制统一字符集
CREATE DATABASE IF NOT EXISTS sk3017_ledger
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
USE sk3017_ledger;
```

```python
# config.py：连接串显式带 charset，不依赖服务端默认值
SQLALCHEMY_DATABASE_URI = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:root@127.0.0.1:3306/sk3017_ledger?charset=utf8mb4",
)
```

另外在建表脚本的每张表末尾补 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;`，防止个别表继承到旧默认值。修复后 emoji 图标（🍜、💼）也能正常存取。

**预防**：① 建库脚本一律显式声明字符集与排序规则，不依赖默认值；② 连接串固定 `charset=utf8mb4` 并写进 `.env.example`；③ 自测清单加入"录入一条含 emoji 和中文的备注"这一项；④ 用 `SHOW VARIABLES LIKE 'character_set%';` 在排障时先确认连接层字符集。

---

## BUG-002 ｜ 09-28 ｜ 第一次跑 `init-db`，Windows 控制台抛 `UnicodeEncodeError`

**现象**：在 Windows 自带的 GBK 控制台（cmd / PowerShell）执行 `flask --app run.py init-db`，建表本身成功，但打印完成提示时直接抛异常：

```text
UnicodeEncodeError: 'gbk' codec can't encode character '\u2714' in position 0: illegal multibyte sequence
```

命令行里看不到"建表完成"的提示，第一次还误以为建表失败，去数据库里确认才发现表已经建好了。

**根因**：CLI 输出用了 `click.secho("✔ 数据表创建完成")`，`✔`（U+2714）不在简体中文 Windows 控制台的默认代码页 GBK（CP936）字符集内；Python 的 `sys.stdout` 在交互式控制台按 GBK 编码输出，遇到无法编码的字符就抛 `UnicodeEncodeError`。这是**输出层**的问题，不影响业务逻辑，但会中断 CLI 流程，让后面的提示都打不出来。

**解决**：CLI 与脚本输出统一改用 ASCII 标记，不再依赖控制台能否显示特殊符号：

```python
click.secho("[OK] 数据表创建完成", fg="green")
click.secho(f"[OK] 已导入 {len(records)} 条记账记录、{len(payload['budgets'])} 条预算", fg="green")
click.secho("[!] 该命令会删除全部数据，确认请加 --yes", fg="red")
```

`database/schema.sql` 末尾的输出也同步改为 `SELECT '[OK] sk3017_ledger 建库建表完成' AS result;`。如果确实需要输出 Unicode，也可以临时设置 `PYTHONUTF8=1` 或 `chcp 65001`，但项目里选择更稳妥的 ASCII 方案。

**预防**：① CLI、日志、部署脚本的输出不使用 GBK 之外的符号（`✔ ✖ ⚠ ℹ` 和 emoji 都不行），统一 ASCII 标记；② 涉及中文输出的脚本在 Windows 控制台实跑一次，不能只在 VS Code 终端（默认 UTF-8）测试；③ 把 `PYTHONUTF8=1`、`chcp 65001` 写进 README 的常见问题，作为备选手段。

---
## BUG-003 ｜ 10-07 ｜ 统计接口 500：`Object of type Decimal is not JSON serializable`

**现象**：概览与饼图接口改完 SQL 聚合后，页面打开统计页直接 500，后端日志：

```text
TypeError: Object of type Decimal is not JSON serializable
```

**根因**：`amount` 字段是 `DECIMAL(10,2)`，SQLAlchemy 映射 `Numeric(10,2)` 后，`Model.amount` 与 `func.sum(...)` 的返回值都是 `decimal.Decimal`。Flask 的 `jsonify` 基于标准 `json` 模块，不认识 `Decimal`；之前手工循环累加时我用了 `float(rec.amount)` 转换，改成数据库聚合后忘了在出口处转换。

**解决**：在 `app/services.py` 里加一个统一的 `_f()` 转换函数，所有聚合结果出口都过它，并显式处理"无数据时 `SUM` 返回 `None`"：

```python
def _f(value) -> float:
    """DECIMAL -> float（保留 2 位小数），None -> 0.0。"""
    if value is None:
        return 0.0
    return round(float(value), 2)

# 聚合结果
total = db.session.scalar(
    db.select(func.coalesce(func.sum(Record.amount), 0)).where(*conditions)
)
return jsonify({"code": 0, "msg": "ok", "data": {"total": _f(total)}})
```

同时给 `Record.to_dict()` 补上 `float(self.amount)`，避免快速记账接口踩同一个坑。

**预防**：① 约定"**计算层 Decimal，展示层 float**"的边界，序列化只在一处做；② 所有聚合查询一律套 `coalesce(sum(...), 0)` 并过 `_money()`；③ 在 `DEBUG_LOG` 之外补一条 pytest 用例断言接口能正常返回 JSON；④ 遇到类型边界问题先看 ORM 字段类型再查 JSON 编码链。

---

## BUG-004 ｜ 10-14 ｜ 登录状态下点"删除"返回 400：`The CSRF token is missing.`

**现象**：流水列表的删除按钮改为 `fetch` 提交后，后端返回 400，响应体是 Flask-WTF 的 `The CSRF token is missing.`；同一页面的普通编辑表单却能正常提交。

**根因**：`CSRFProtect` 对**所有 POST** 校验 token，普通表单靠隐藏域 `{{ csrf_token() }}` 自动带上；而 `fetch` 请求只发了 JSON body，没有携带 token。Flask-WTF 从 `form.csrf_token`、`X-CSRFToken` 请求头、`X-CSRF-Token` 请求头三处找 token，`fetch` 默认一个都没带。

**解决**：在 `base.html` 的 `<head>` 注入 meta，统一在公共 JS 里读取并附加请求头：

```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

```javascript
function csrfHeaders(extra = {}) {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
  return { 'X-CSRFToken': token, ...extra };
}

await fetch(`/records/${id}/delete`, {
  method: 'POST',
  headers: csrfHeaders({ 'X-Requested-With': 'XMLHttpRequest' }),
});
```

**预防**：① 所有非表单写操作统一走一个 `request()` 封装，token 只在封装里读取一次；② 新增 Ajax 接口时自测"无 token 应 400、有 token 应成功"；③ 把 CSRF 失败视图指向自定义错误页，避免直接把 Flask-WTF 的英文提示暴露给用户。

---

## BUG-005 ｜ 10-15 ｜ 手动把 URL 改成 `?page=abc`，页面直接 500

**现象**：流水页翻页正常，但地址栏把 `page` 改成 `abc` 或 `-1` 后返回 500，日志是 `ValueError: invalid literal for int() with base 10: 'abc'`。

**根因**：路由里直接 `page = int(request.args.get("page", 1))`。分页参数来自 URL，完全由用户控制，非数字、负数、超大值都会让 `int()` 抛异常；`page=-1` 还会算出负的 `offset`，MySQL 会报 `You have an error in your SQL syntax`，同样是 500。

**解决**：抽出统一的 `parse_int`，类型与范围错误都转成 `ValidationError`；分页参数属于"浏览态"参数，非法值**回落第 1 页**而不是报错：

```python
def parse_int(raw, field, minimum=1, maximum=999999, default=None):
    if raw is None or str(raw).strip() == "":
        if default is not None:
            return default
        raise ValidationError(f"{field}不能为空")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field}必须是整数")
    if value < minimum or value > maximum:
        raise ValidationError(f"{field}超出允许范围（{minimum} ~ {maximum}）")
    return value

# 路由内
try:
    page = parse_int(request.args.get("page"), "页码", default=1)
except ValidationError:
    page = 1
```

**预防**：① 所有来自 query string / form 的整数一律走 `parse_int`，禁止裸 `int()`；② 分页统一用 ORM 的 `db.paginate` 并限制 `max_per_page`；③ 测试补 `?page=abc`、`?page=-1`、`?page=999999` 三条用例。

---

## BUG-006 ｜ 10-17 ｜ 切换到没有数据的月份，折线图 X 轴出现 NaN、图表一片空白

**现象**：统计页 10 月有数据时正常；筛选切到 9 月（无记录）后，控制台报 `ECharts: Invalid data`，折线图区域空白，X 轴刻度显示 `NaN`。

**根因**：后端直接返回 `GROUP BY record_date` 的结果，9 月无记录时 `labels` 与 `expense` 都是空数组。ECharts 在空数据下会尝试用 `Math.min/max` 计算坐标轴范围，得到 `Infinity/NaN`；同时我的折线配置里写了 `xAxis: { type: 'category' }`，空分类轴导致渲染异常。另一个隐患是：有数据但只有 4 天时，折线会把这 4 个点直接相连，视觉上误导为连续消费。

**解决**：后端按"当月完整日期序列"补零，保证任意月份都返回 28~31 个刻度；前端空数据时不渲染图表，改为显示空状态：

```python
first, last = month_range(year, month)
rows = {r.record_date: r.total for r in query.all()}
labels, values = [], []
day = first
while day <= last:
    labels.append(day.isoformat())
    values.append(_money(rows.get(day, 0)))
    day += timedelta(days=1)
```

```javascript
function renderDailyTrend(data) {
  if (!data.labels.length) { showChartEmpty('dailyChart', '当月暂无支出记录'); return; }
  dailyChart.setOption({ xAxis: { data: data.labels }, series: [{ data: data.expense }] }, true);
}
```

**预防**：① 所有"按时间分组"的图表接口都由后端补零，前端不做日期计算；② 每个图表组件都实现 `showChartEmpty` 分支；③ 自测时必须覆盖"完全无数据""只有一天有数据"两种极端情况。

---

## BUG-007 ｜ 10-18 ｜ 统计查询在日期上做字符串比较，`EXPLAIN` 显示全表扫描

**现象**：把筛选参数直接透传给 SQL 后，`EXPLAIN` 显示 `type=ALL`、`rows` 等于全表行数；在 500 条数据下页面还能忍，seed 到 3000 条后统计接口明显变慢。同时发现 `record_date` 传 `'2026-10-1'`（缺前导零）时能被 MySQL 隐式转换但范围结果错乱。

**根因**：两个问题叠加。① 日期条件写成了 `func.date_format(Record.record_date, '%Y-%m') == "2026-10"` 或 `func.year(...)`，列被函数包裹后无法使用 `ix_record_user_date`；② 参数以字符串 `'2026-10-01'` 与 `DATE` 列比较，MySQL 会做隐式类型转换，在边界值上产生歧义（如 `'2026-10-1'` 与 `'2026-10-01'` 比较行为不同），也影响优化器选择索引。

**解决**：日期参数一律先经 `parse_date` 转成 `datetime.date`，SQL 侧只用裸列区间：

```python
start, end = month_range(year, month)   # 返回 date 对象，闭区间
conditions = [
    Record.user_id == current_user.id,
    Record.record_date >= start,
    Record.record_date <= end,
]
stmt = db.select(Record).where(*conditions).order_by(Record.record_date.desc())
```

修复后 `EXPLAIN` 显示 `type=range`、`key=ix_record_user_date`。趋势图的年月分组改到 Python 侧按 `(record_date.year, record_date.month)` 分桶，避免使用 MySQL 专有的 `DATE_FORMAT`。

**预防**：① 规定"日期列上不允许出现函数"，一律区间比较；② 所有日期参数必须经过 `parse_date` 变成 `date` 对象再进查询；③ 在 `tests/` 里对关键聚合加 `EXPLAIN` 手工核对清单，写进设计文档 5.7。

---

## BUG-008 ｜ 10-21 ｜ 同一个月连续保存两次预算，第二次直接 500

**现象**：预算页第一次保存成功，修改金额再点保存，页面报 500，日志：

```text
sqlalchemy.exc.IntegrityError: (pymysql.err.IntegrityError) 1062 Duplicate entry '1-2026-10' for key 'budget.uq_budget_user_month'
```

**根因**：保存逻辑是"先查有没有，没有就 `INSERT`"，但页面表单在首次保存后没有正确回传"已存在"标识（前端判断字段没带 `id`），于是第二次仍走 `INSERT`；数据库的唯一约束 `uq_budget_user_month` 兜住了重复数据，但 `IntegrityError` 没有被捕获，变成了 500。这也说明**唯一约束确实生效了**，是应用层没处理好。

**解决**：改为"先查后更新"的 upsert 逻辑，应用层不再无脑 `INSERT`；唯一约束保留，作为并发请求下的最后一道防线：

```python
budget = Budget.query.filter_by(
    user_id=current_user.id, year=year, month=month
).first()
if budget is None:
    budget = Budget(user_id=current_user.id, year=year, month=month, amount=amount)
    db.session.add(budget)
else:
    budget.amount = amount          # 已存在就更新，而不是再插一条
db.session.commit()
```

**预防**：① "查询后插入"的写法一律按 upsert 处理，优先"先查后更新"；② 凡是带唯一约束的表，写入前必须做存在性检查，并明确"重复时是更新还是报错"的产品语义；③ 前端保存成功后回填当前月份，避免重复提交。

---

## BUG-009 ｜ 10-22 ｜ 未登录时点统计筛选，控制台报 `Unexpected token '<'`

**现象**：会话过期后停留在统计页，点击年月筛选，控制台报 `SyntaxError: Unexpected token '<', "<!doctype "... is not valid JSON`，页面无任何提示。

**根因**：`@login_required` 对未登录请求返回 302 跳转登录页，`fetch` 默认 `redirect: 'follow'` 会跟随跳转拿到登录页的 HTML（以 `<!doctype html>` 开头），前端直接 `res.json()` 解析 HTML，于是抛语法错误。更深层的问题是**页面请求与接口请求用了同一套"未登录"处理策略**，但两者的合理响应完全不同：页面应跳转，接口应返回 401 JSON。

**解决**：后端在鉴权失败时按请求类型分流，前端封装层再兜底：

```python
@login_manager.unauthorized_handler
def unauthorized():
    if _wants_json():
        return jsonify({"code": 1, "msg": "登录已过期，请重新登录"}), 401
    flash("请先登录后再继续操作。", "warning")
    return redirect(url_for("auth.login", next=request.path))
```

```javascript
async function request(url, options) {
  const res = await fetch(url, options);
  if (res.redirected && res.url.includes('/login')) { location.href = res.url; throw new Error('未登录'); }
  if (res.status === 401) { location.href = '/login'; throw new Error('未登录'); }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).msg || '请求失败');
  return res.json();
}
```

**预防**：① 接口与页面的鉴权失败响应分开设计，接口统一 401 JSON；② 前端所有请求走同一 `request()` 封装，禁止直接 `res.json()`；③ 在接口文档中明确写出"401 = 未登录/会话过期"。

---

## BUG-010 ｜ 10-24 ｜ 没有设置预算的月份，概览页进度条显示 `NaN%` 或除零异常

**现象**：新用户注册后未设置预算，首页概览直接空白；日志里偶发 `ZeroDivisionError: division by zero`，去掉异常后进度条宽度变成 `NaN`，`width: NaN%` 被浏览器忽略，进度条不显示。

**根因**：预算使用率计算写成 `usage = spent / budget_amount * 100`。未设置预算时 `Budget` 记录不存在，`amount` 取到 `None` 或 0；即使做了 `amount or 0`，`spent / 0` 仍然除零。前端又直接把这个值塞进 `style.width`，于是渲染出非法的 CSS 值。

**解决**：后端把"没有预算"作为一种正常状态返回明确的语义字段，前端按 `level` 分支渲染：

```python
# services.budget_status：amount 为 0 视为未设置预算，不做除法
amount = _f(budget.amount) if budget else 0.0
usage = round(expense / amount * 100, 1) if amount > 0 else 0.0
if amount <= 0:
    level = "none"
elif usage >= 100:
    level = "over"
elif usage >= 80:
    level = "warn"
else:
    level = "normal"
return {"amount": amount, "spent": expense, "remain": round(amount - expense, 2),
        "usage": usage, "level": level}
```

前端：`level === "none"`（`amount <= 0`）时显示"本月还没设置预算，去设置"，不渲染进度条；`level === "over"` 时显示"已超支 ¥xx"，红色；`remain` 为负数时不再直接塞进 `style.width`。

**预防**：① 所有除法先判分母，业务上"未设置"用独立状态（`level="none"`）表达而不是硬算百分比；② 百分比、进度类字段在接口层就给出明确取值，前端只做展示分支；③ 测试补"新用户无预算访问首页"用例。

---

## BUG-011 ｜ 10-26 ｜ 年度热力图全年无支出时整块变成空白

**现象**：热力图接口在当年无任何支出时返回 `{"year":2026,"max":0,"values":[]}`，ECharts 图表区域一片白；把 `max` 手动改成 10 后，格子仍然没有颜色。

**根因**：两个问题叠加。① `visualMap.max` 取的是全年单日支出的最大值，无数据时 `max = 0`，ECharts 用 `max - min` 计算色阶映射，分母为 0 无法映射颜色；② 我的代码在 `values` 为空时仍然调用了 `setOption`，ECharts 在空数组上初始化日历坐标系，部分版本会直接不渲染。

**解决**：后端保证 `max` 与 `values` 的语义自洽（无数据时 `max` 为 0 但 `values` 为空）；前端把"无数据"和"有数据"分成两条渲染路径：

```python
# services.heatmap
values = [[day.isoformat(), _f(total)] for day, total in rows]
max_value = max([v[1] for v in values], default=0.0)
return {"year": year, "max": round(max_value, 2), "values": values}
```

```javascript
if (!data.values.length) { showChartEmpty('heatmapChart', '该年度暂无支出记录'); return; }
heatmapChart.setOption({ visualMap: { max: Math.max(1, data.max) }, series: [{ data: data.values }] }, true);
```

即"接口如实返回空数据，前端不把空数组交给图表库"，并在渲染时给 `visualMap.max` 一个至少为 1 的下限，避免色阶除零。

**预防**：① 凡是"取最大值作为分母"的图表配置（热力图、色阶）都要给下限；② 空数组一律走空状态分支，不交给图表库自行处理；③ 自测覆盖"全年无数据""只有一天有数据""超大金额"三种情况。

---

## BUG-012 ｜ 10-29 ｜ 导出的 CSV 用 Excel 打开，中文全部乱码

**现象**：浏览器下载 `records_2026-10.csv` 后用 Excel 双击打开，"日期/类型/分类"表头和中文备注全部显示为乱码（`鏃ユ湡`、`绫诲瀷` 这类），用 VS Code 打开却正常。

**根因**：文件内容以 UTF-8 编码写出，但没有 BOM。Excel 在 Windows 下对无 BOM 的 `.csv` 默认按系统 ANSI（简体中文环境为 GBK/CP936）解码，UTF-8 的中文字节被按 GBK 解释，于是乱码。VS Code 能自动嗅探 UTF-8，所以看起来正常，容易误判"文件没问题"。

**解决**：CSV 字节流用 `utf-8-sig` 编码，写入时自动带 BOM：

```python
def build_records_csv(records) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["日期", "类型", "分类", "账户", "金额", "备注"])
    for rec in records:
        writer.writerow([...])
    return buffer.getvalue().encode("utf-8-sig")   # 关键：BOM
```

同时把中文文件名编码成 ASCII 的 `filename*` 参数，避免下载时文件名乱码（这一段的具体踩坑见 BUG-013）：

```python
encoded = quote(filename, safe="")
return Response(
    payload,
    mimetype="text/csv",
    headers={
        "Content-Disposition": f"attachment; filename=records.csv; filename*=UTF-8''{encoded}",
        "Cache-Control": "no-store",
    },
)
```

**预防**：① 面向 Excel 的 CSV 导出统一用 `utf-8-sig`，并在 README 常见问题里写明；② 自测时用 Excel 实际打开验证，不能只看编辑器；③ 不要把"VS Code 显示正常"当作编码正确的依据。

---

## BUG-013 ｜ 10-30 ｜ 下载 CSV 在真实 WSGI 服务器上报 `UnicodeEncodeError: 'latin-1' codec can't encode characters`

**现象**：用 `pytest`/`test_client` 测导出的 header 一切正常；用 `python run.py` 启动后在浏览器点"导出 CSV"，服务器直接 500，日志：

```text
UnicodeEncodeError: 'latin-1' codec can't encode characters in position 21-40: ordinal not in range(256)
```

**根因**：WSGI 规范要求响应头必须是 latin-1 可编码的字节串。我把中文文件名 `账目明细_20261030_193000.csv` 直接拼进 `Content-Disposition`，开发服务器在真正写响应时按 latin-1 编码失败。`test_client` 只构造 `Response` 对象、不经过 WSGI 服务器编码，所以测试完全掩盖了这个问题。

**解决**：文件名先做 URL 编码，响应头里只出现 ASCII；同时保留一个 ASCII 兜底文件名：

```python
from urllib.parse import quote

filename = f"账目明细_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
encoded = quote(filename, safe="")
return Response(
    payload,
    mimetype="text/csv",
    headers={
        "Content-Disposition": f"attachment; filename=records.csv; filename*=UTF-8''{encoded}",
        "Cache-Control": "no-store",
    },
)
```

测试相应改为断言 header 全部是 ASCII，并断言 `filename*=UTF-8''` 前缀存在。

**预防**：① 响应头只允许 ASCII，任何中文/emoji 必须先编码；② 涉及响应头的功能必须用真实服务器（`python run.py`）点一遍，不能只跑 `test_client`；③ 补一条"header 编码全 ASCII"的断言，把这类问题挡在回归测试里。

---

## BUG-014 ｜ 10-30 ｜ `/healthz` 返回 500：`ImportError: attempted relative import beyond top-level package`

**现象**：健康检查接口 `GET /healthz` 返回 500，日志显示 `ImportError: attempted relative import beyond top-level package`；其他页面正常。

**根因**：`app/errors.py` 是 `app` 包下的**模块**（不是子包），里面写了 `from ..extensions import db`。两个点表示"上一级包"，对 `app.errors` 来说会越出 `app` 顶层包，Python 直接拒绝。

**解决**：改为同级导入：

```python
# app/errors.py
from .extensions import db
```

并补 `tests/test_pages.py::test_healthz_ok` 用例，真实走一遍路由。

**预防**：① 区分"包（带 `__init__.py` 的子目录）"与"模块（单文件）"的相对导入层级；`app/xxx.py` 内只能用单点；② 新增路由后至少有一个 HTTP 级测试覆盖，避免"写了但没跑过"；③ 部署脚本把 `/healthz` 纳入启动自检。

---

## BUG-015 ｜ 10-30 ｜ 页面能打开但 JS/CSS 不生效，浏览器拒绝执行脚本

**现象**：本机 Chrome 打开页面，布局正常但交互全失效，Console 报：

```text
Refused to execute script from '.../js/app.js' because its MIME type ('text/plain') is not executable
```

**根因**：Windows 注册表里 `.js` 的 MIME 类型被某些软件改成了 `text/plain`，Python 的 `mimetypes` 模块读取系统注册表后，Flask 静态文件响应就把 `app.js` 标成 `text/plain`。现代浏览器对脚本执行做严格 MIME 校验，于是拒绝执行。换一台机器就正常，属于典型的"环境相关"问题。

**解决**：在 `create_app()` 开头显式登记静态资源类型，不依赖操作系统：

```python
import mimetypes

def create_app(config_name="default"):
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    ...
```

测试用 `response.mimetype == "application/javascript"` 断言，防止回归。

**预防**：① 静态资源的关键 MIME 类型在应用里显式登记，不信任系统注册表；② 自测时打开浏览器开发者工具确认 Network 里的 `Content-Type`；③ 页面"能打开但没样式/没交互"时，优先怀疑 MIME 与静态资源加载，而不是业务代码。

---

## BUG-016 ｜ 10-30 ｜ 打开"记一笔"页面报 `UndefinedError: 'errors' is undefined`

**现象**：点击导航里的"记一笔"（GET `/records/create`）直接 500，日志 `jinja2.exceptions.UndefinedError: 'errors' is undefined`；而表单提交失败后重新渲染同一模板却正常。

**根因**：`record_form.html` 里访问了 `errors` 和 `values` 两个变量。`_record_form_context()` 返回的字典本身只有 `record/categories/accounts/is_edit/today_str`，GET 分支又用 `{k: v for ... if k not in ("errors", "values")}` 把这两个键过滤掉，于是模板拿到的是未定义变量；POST 分支显式传了 `errors` 与 `values`，所以只有 GET 崩。

**解决**：去掉"过滤键"的写法，让每个渲染分支都显式传齐模板需要的变量：

```python
# 新建（GET）
return render_template(
    "ledger/record_form.html",
    errors={},
    values={},
    action_url=url_for("ledger.record_create"),
    **_record_form_context(),
)

# 编辑（GET）：回填原值
values = {
    "amount": f"{float(record.amount):.2f}",
    "type": record.type,
    "category_id": record.category_id or "",
    "account_id": record.account_id or "",
    "record_date": record.record_date.strftime("%Y-%m-%d"),
    "note": record.note or "",
}
return render_template(
    "ledger/record_form.html",
    errors={},
    values=values,
    action_url=url_for("ledger.record_edit", rid=rid),
    **_record_form_context(record),
)
```

**预防**：① 同一模板的每个渲染分支都要传齐模板变量，不用"过滤掉某些键"的小聪明写法；② 对每个页面补 GET 冒烟测试（`tests/test_pages.py` 覆盖全部页面渲染）；③ 模板里不要用 `|default` 掩盖"变量根本没传"的问题，宁可报错早暴露。

---

## BUG-017 ｜ 10-30 ｜ 把账户改名成已有名称，页面直接 500

**现象**：在「账户管理」里把自定义账户「校园卡」改成「微信」（已存在）后提交，页面返回 500，日志报 `sqlalchemy.exc.IntegrityError: (1062, "Duplicate entry '1-微信' for key 'account.uq_account_user_name'")`；改成不冲突的名字则一切正常。

**根因**：`account` 表上有 `UNIQUE(user_id, name)` 约束，`create_account` 里做了同名判断，但 `update_account` 只校验了"名称非空、长度、类型合法"，**漏了改名时的重名判断**。唯一约束是在 `commit()` 时才由数据库抛出的，此时异常已经从库里冒到路由层，被兜底成 500。

**解决**：改名时先按"排除自己"的方式查一次同名：

```python
# ledger.update_account：改名同样要判重，否则会撞 uq_account_user_name 直接 500
duplicated = Account.query.filter(
    Account.user_id == _uid(), Account.name == name, Account.id != account.id
).first()
if duplicated:
    flash("已存在同名账户", "warning")
    return redirect(url_for("ledger.accounts"))
```

并在 `tests/test_stats.py` 补了回归用例 `test_update_account_duplicate_name_rejected`，断言返回 200 且提示「已存在同名账户」。

**预防**：① 凡是有数据库唯一约束的字段，**新增和修改两条路径**都要做业务层判重，不能只依赖数据库；② 数据库约束是最后一道防线，触发时应由全局 `IntegrityError` 处理转成友好提示（本次先补业务校验，全局兜底列入改进项）；③ 修改类接口的测试必须包含"改成冲突值"这种反向用例，只测"改成功"会漏。

---

## 复盘小结

### 一、问题分类统计

| 分类 | 数量 | 编号 | 典型特征 |
| --- | --- | --- | --- |
| 数据正确性 / 类型边界 | 5 | BUG-003、BUG-007、BUG-008、BUG-010、BUG-017 | Decimal 与 float、日期类型、唯一约束、除零 |
| 前端与接口契约 | 5 | BUG-004、BUG-006、BUG-009、BUG-011、BUG-016 | CSRF、空数据、未登录 302、图表分母为 0、模板变量未定义 |
| 环境与编码 | 5 | BUG-001、BUG-002、BUG-012、BUG-013、BUG-015 | 数据库字符集、Windows 控制台、CSV BOM、响应头 latin-1、静态资源 MIME |
| 输入健壮性 | 1 | BUG-005 | 分页参数非法值 |
| 代码结构 | 1 | BUG-014 | 相对导入层级越界 |

从分布看，**真正"写错逻辑"的 bug 很少，多数是"边界没定义清楚"**：空数据、无预算、未登录、非法参数、无 BOM。这些场景在正常演示路径上都不会出现，但恰恰是评分老师和用户最容易随手触发的地方。

### 二、共性根因

1. **"正常路径"思维**：开发时默认数据存在、参数合法、用户已登录，缺少对"空 / 零 / 无 / 非法"的系统性走查。
2. **类型边界模糊**：`Decimal` 与 `float`、`date` 与 `str`、`None` 与 `0` 混用，问题往往在跨层（Python → JSON → JS）时才暴露。
3. **前后端契约不明确**：未登录、CSRF 失败、接口报错三种情况缺少统一约定，导致前端只能靠猜。
4. **只在自己环境验证**：数据库字符集依赖默认值、CSV 只用编辑器看过，没有在真实 MySQL / Excel 上验证。

### 三、下一阶段的改进

1. **建立边界自测清单**：每个功能交付前对照"空数据、无权限、非法参数、极限数值、跨边界日期"五项走一遍，把清单写进 `docs/` 作为验收依据。
2. **接口契约先定后写**：先写接口文档（返回结构、错误码、空值语义），再写代码，避免前后端各说各话（本次 `docs/接口文档.md` 就是事后补的，代价更高）。
3. **每个 BUG 补一条回归测试**：目前 17 个 bug 中已有 11 个沉淀为 pytest 用例，剩余 6 个（浏览器渲染、命令行环境、Excel 验证类）计划改为手工检查项或前端断言。
4. **重视"演示环境"而不是"开发环境"**：断网、Excel、Windows 中文系统、手机浏览器这四个场景在答辩前要专门跑一遍。
5. **日志与错误码规范化**：后端异常统一记录 `logger.exception`，对外只暴露 `code/msg`，便于定位又不泄露堆栈。
