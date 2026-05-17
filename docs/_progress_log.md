4.25
✅ SSH key、Git、GitHub 仓库
✅ Dockerfile、docker-compose.yml、.env、.dockerignore
✅ Python + PostgreSQL 容器化环境跑通
✅ 端到端验证（容器互通、psql 连数据库）

4.26
✅ Create raw_oncap.employer_registry table

4.27
✅ Create raw_oncap.member_census table
✅ Create raw_oncap.member_census_control table
✅ Create raw_oncap.transaction table

4.28
✅ Create raw_oncap.life_event table
✅ Create raw_oncap.portal_event table
✅ Create raw_oncap.call_log table
✅ Create raw_oncap.seminar_attendance table

5.10
Week 4 先做 A(full refresh),Week 6-7 等 dbt marts 跑通后,挑 1-2 张表改成 incremental 作为"懂这个概念"的展示。简历讲法:"loader 支持 full refresh,核心 fact 表用 incremental 策略"——完全成立。

## 2026-05-16 — Week 4 Day 1

**Done:**
- employer_registry 加 acquisition 字段(channel/source/first_contact_date),重生成 + 重 load
- 字段设计:channel 5 类,source 6 类,channel 驱动 sales_cycle 范围
- DDL + _config.py + record_layouts.md 三处同步更新
- glob pattern 从 *.csv 改为 ONCAP001_EMPLOYER_REGISTRY_*.csv

**Stuck:**
- 备份文件放在 generator 输出同目录,被 *.csv glob 扫到当 input 加载。
  truncate-and-load 救场,但教训记下:loader glob 应该显式前缀过滤,
  不靠"约定俗成放别处"。
- awk -F',' 不懂 CSV 引号转义,误报 27 个 violations。验证 csv 必须用 python csv 模块。

**Next (Day 2, 5/17):**
- cra_t3010 入 raw_external schema:新建 schema、csv_format 应该够用、新 TableConfig 入 _config.TABLES。
- 注意 T3010 文件有 BOM + cp1252 编码问题(参考 generator 里的 _read_csv_with_encoding_fallback),loader 可能需要支持 encoding 参数å

## 2026-05-17 — Week 4 Day 1

**Done:**
- 建 raw_external / stg_external / mart_external 三个 schema(对称命名)
- 02_raw_external_tables.sql:t3010_ident (12 列) + t3010_schedule3 (16 列,含 "300"/"370" 等 CRA 线代码列)
- TableConfig 加 encoding 字段(默认 utf-8) + source_header 字段(默认 None)
- csv_format / pipe_format / jsonl_format 加 encoding kwarg;csv_format 加 source_header kwarg
- _db.py dispatch 三分支:fixed_width / csv / pipe-jsonl,显式传各自需要的参数
- _db.py COPY 列名加双引号(为支持 schedule3 的 "300" 等数字列名)
- t3010_ident 84k 行入库,t3010_schedule3 43k 行入库
- 回归 employer_registry / transaction / portal_event 全绿

**Stuck:**
- 第一次 T3010 load 失败:csv_format 严格字面量匹配 header,但 DDL 用 snake_case 列名 vs 源文件 "Legal Name" 等。教训:csv_format 的 column_mismatch 校验是 raw-load 的 contract,不该靠"约定俗成"。引入 source_header 字段把 DDL 标识符和源 header 解耦。
- 选 D 不选 E 的判断:E (DDL 用源文件原名 + 双引号查询) 看似 cosmetic 小代价,实际把双引号税推给所有下游(dbt、debug、临时查询)。D 在入口一次解决,改动只有几行。
- schedule3 的 "300"/"370" 数字列名躲不掉双引号——dbt staging 第一步用 AS rename。

**Observation:**
- t3010_schedule3 (43k) 是 t3010_ident (84k) 的一半。小 charity 不填 schedule 3 很常见。
- 400 个 employer 应该都 match ident(generator 从 ident 选),但不一定都 match schedule3 (~75% 估计)。Week 6 employer enrichment 走 left join。

**Next (Day 3, 5/18):**
- _load_audit 表 + metadata 记录(load_run_id / started_at / row_counts / source_file)
- 这是 Python loader 收尾,之后 loader 故事完整,Week 5 起进 dbt 主线


## 2026-05-17 — Week 4 Day 2

**Done:**
- raw_oncap._load_audit DDL:表级粒度,success/failed 都写,JSONB 存 per-file 明细
- _db.py 加 audit 逻辑:独立 connection 写 audit,失败事务 rollback 不丢 audit
- audit 写 best-effort:audit 自身失败打 warning 不 re-raise
- sanity test 两种 failure path:csv 列错(ValueError 在 COPY 前)+ 表不存在(UndefinedTable 在 TRUNCATE)
- 全表 `load --all` 跑通:10 张表,728k 行,1.3 秒内全部入库
- audit 表累积 13 行真实运行记录(11 success + 2 failed sanity)

**Design notes:**
- _rejected vs _load_audit 职责分工:行级 vs 调用级。production ETL 标配两表。
- 失败路径下 audit 的 rows_good/files_loaded 记的是"挂前处理了多少"(诊断价值),不是 db 实际状态(rollback 为 0)。DDL comment 说明这点。

**Python Loader 整条线完工:**
- 4 种格式(csv/pipe/jsonl/fixed_width),内容驱动
- 行级 reject + 文件级 reject + 全量 audit + 事务隔离 + multi-encoding + header alias
- 2 schema(raw_oncap + raw_external),10 张表
- ~728k 行,最大单表 227k 行,1s 内入库

Week 5 起 loader 不再修改,作为上游基础设施服务下游 dbt/Snowflake。

**Next (Day 4, 5/18):**
- Snowflake setup 整个流程清醒头脑做
- Pre-work:申请账号 / region 选 us-east / standard edition / 设 cost monitoring
- 6 schema 镜像 Postgres / 翻译 DDL(BIGSERIAL→AUTOINCREMENT / JSONB→VARIANT / TIMESTAMPTZ→TIMESTAMP_TZ)
- 不在 Day 4 做数据迁移,留给 Day 5(`COPY INTO` from stage)


## 2026-05-17 — Week 4 Day 4

**Done:**
- Snowflake account objects 起步:WAREHOUSE PENSION_WH (XSMALL, AUTO_SUSPEND=60s)
  / DATABASE PENSION_DEV / 6 schema 镜像 Postgres / ROLE PENSION_DEVELOPER + grants
- Role 挂到 user ONCAP,设默认 role+wh
- raw_oncap 12 张表 + raw_external 2 张表 DDL 翻译并入库
- 翻译规则统一:TEXT→STRING / TIMESTAMPTZ→TIMESTAMP_TZ / JSONB→VARIANT /
  BIGSERIAL→BIGINT AUTOINCREMENT / now()→CURRENT_TIMESTAMP() / 删 INDEX 和 CHECK

**Stuck:**
- Snowsight worksheet 跑多条 SQL 时,默认只显示最后一条结果。文件 2 第一次跑时,
  顶部 USE SCHEMA 在 db=NULL 上下文失败,但后续 CREATE TABLE 被静默跳过,
  我以为成功其实没建出来。教训:DDL 文件顶部必须自带完整 4 行 context
  (role/wh/db/schema),不依赖 worksheet 当时状态。
- SHOW TABLES / SHOW DATABASES 在 Snowsight UI 的显示行为不稳定;
  INFORMATION_SCHEMA / ACCOUNT_USAGE 是更可靠的诊断面。

**Design notes:**
- _rejected 和 _load_audit 暂时是空表。Day 5 COPY INTO 设计时再决定怎么
  把 COPY INTO 的 reject 路由到 _rejected、把每次调用记一条 _load_audit。
- 备选:Snowflake 内置 INFORMATION_SCHEMA.COPY_HISTORY + LOAD_HISTORY 自动
  记录 COPY,可能两边都用(内置 = ground truth,自定义 = narrative-friendly)。
- CHECK 约束在 Snowflake 没了(语法不支持),_load_audit.status 的
  'success'/'failed' 约定靠代码侧保证。改动很小,几乎没成本。

**Next (Day 5, 5/18):**
- COPY INTO 设计 + 实现:本地文件 → Snowflake stage → raw_oncap/raw_external
- 14 张表全量过一遍
- Snowflake stage 类型选择:internal named stage vs user stage vs table stage
- ON_ERROR 策略 + 是否同步写 _rejected / _load_audit