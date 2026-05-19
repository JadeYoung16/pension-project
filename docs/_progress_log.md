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

## 2026-05-17 — Week 4 Day 5(上半段)

按计划 Day 5 = 5/18,Day 4 同日(5/17)收口后直接接 Day 5。Day 5 工作量预估
4.5h,今天只完成约 2.5h,COPY INTO 整段(Step 4 起)留明天。

**Done:**
- Day 5 4 个设计点全部拍板:
  1. Stage = named internal, 共享 + 子目录分表
  2. File format = 3 个(CSV/PIPE/JSON),fixed-width 走选项 (a) Python 预处理
  3. ON_ERROR = CONTINUE,Day 5 不写自定义 _rejected/_load_audit,先用
     Snowflake 内置 COPY_HISTORY 当 ground truth,自定义留 Day 6+ 时间富裕再补
  4. Transaction T 行处理倾向 (a) 本地预处理拆 detail/control 两 csv,
     和 fixed-width 同思路;但 Day 5 时间紧时可用 (c) 先 ON_ERROR=CONTINUE
     跳过 T 行,control 表后补
- sql/snowflake/03_stage_and_formats.sql:LOAD_STAGE + 3 file format
- loaders/snowflake/__init__.py + test_connection.py + put_files.py
- PUT 144 文件到 stage(transaction 18 + life_event 24 + portal_event 91 +
  4 个 csv 系列 = 144,member_census 2 个 .DAT 暂跳)

**Stuck:**
- `.env` 改完密码 / role / database 不生效。原因:`docker compose restart`
  不重读 env_file,**必须 `down + up`**。教训:Postgres loader 全程没遇到
  过这个,因为 PG 凭证从一开始就稳定;Snowflake 是第一次需要改 .env,
  踩到了。下次改 .env 直接 down+up,不试 restart。
- `.env` 里残留 5/10 学习项目的旧值(PENSION_DW / COMPUTE_WH /
  ACCOUNTADMIN),改 .env 时一次性清掉。教训:.env 是单一真相源,
  老配置不及时清就会变干扰。

**Security incident:**
- Day 5 中段 sanity 检查 `docker compose exec app env` 时**密码明文贴出**。
  对话即使私密也算泄露;Snowsight 已重置密码,.env 同步更新。今后贴 env
  输出统一加 `sed 's/PASSWORD=.*/PASSWORD=***REDACTED***/'`。

**Design notes:**
- PUT 单条支持 glob,91 个 jsonl 一条 PUT 而非 91 次循环,Snowflake 客户端
  内部 PARALLEL=4 并发。预期对大表(transaction / portal_event)上传时间
  从分钟降到秒。
- METADATA$FILENAME + METADATA$FILE_ROW_NUMBER 是 Snowflake 原生 stage
  metadata 函数,COPY INTO 里直接当审计列写入,完全免去 Postgres loader
  那种"Python 拼接 _source_file/_row_num 进 StringIO"的胶水。Day 5 第一
  张表的 COPY 模板用 SELECT $1..$N + METADATA$* 一次跑通,剩下 13 表照搬。

**Next (Day 5 下半段, 5/18):**
- Step 4: COPY INTO employer_registry(最小表,验证模板)
- Step 4b: 剩下 9 张 csv/pipe/jsonl 表 COPY INTO
- Step 5: member_census 预处理脚本(复用 fixed_width_format.py)→ csv → PUT → COPY INTO
- Step 6: T3010 两表 COPY INTO
- Step 7: 全表 row count 对账(Snowflake vs Postgres 14 表)
- Step 8: commit + progress log
- 不挪用 buffer 的话,Day 5 全部完成 = 5/18 全天

**Open question 留明天决定:**
- transaction T 行走 (a) 还是 (c)?Day 5 头部时间充裕走 (a),时间紧再降到 (c)
- _rejected / _load_audit 在 Snowflake 这边什么时候补?Day 6 (dbt 起跑前)还是 Day 7+?

## 2026-05-18 — Week 4 Day 5(下半段)

承接昨天 Day 5 上半段(stage + put 完成)。今天目标:Step 4-7 跑完
(COPY INTO 14 张表 + 对账)。实际完成 8/14 + 部分对账,余 2 张 t3010 表
+ 完整对账,留明天 5/19 收尾。

**Done:**
- Step 4: employer_registry COPY INTO 模板验证(400 行,跟 Postgres 一致)
- Step 4b 完成 6 张表:
  - call_log (4,122) / seminar_attendance (5,816) / email_engagement (227,502)
  - life_event (17,638, SKIP_HEADER=1)
  - transaction (186,865, SKIP_HEADER=2, ON_ERROR=CONTINUE 跳 T 行)
  - portal_event (58,537 ≠ Postgres 59,606,详 Known issue)
- Step 5: member_census 预处理 + PUT + COPY INTO 通(100,000 行)
- 8/14 表对账与 Postgres 一致

**Known issue: portal_event 行数差异**
- Postgres raw_oncap.portal_event: 59,606
- Snowflake RAW_ONCAP.PORTAL_EVENT: 58,537(差 1,069 = 1.8%)
- 原因:Snowflake TYPE=JSON parser 容错粒度是**文件级**,
  ON_ERROR=CONTINUE 遇到 malformed JSON 时跳过整个文件剩余行,而不是
  Postgres jsonl_format.py 那种行级 reject。5 个文件 partially loaded,
  每个 error_count=1,但累计丢了 ~1069 行。
- 影响评估:raw 层不完整;mart 层(member-month 聚合)受影响极小。
- 修法:Day 6 用 TRY_PARSE_JSON 实现行级 reject(整文件读为 STRING,
  WHERE TRY_PARSE_JSON IS NOT NULL 过滤再 INSERT)。Day 5 不补,推进
  member_census 优先。

**Stuck/lessons:**
- ON_ERROR=CONTINUE 行为**因 file format 而异**:CSV/PIPE 是行级
  reject,JSON 是文件级。Snowflake 文档对此不显式。教训:多 format 项目
  里 raw 层完整性必须**按格式分别验证**,不能假设统一行为。
- Snowflake LOAD_HISTORY 去重:同名文件 64 天内不重复加载,COPY 返回
  "0 files processed"。开发期容易误以为失败,要看 INFORMATION_SCHEMA
  COPY_HISTORY 或者直接 SELECT COUNT(*) 对账。
- Snowsight worksheet 多语句 USE 后,后续命令 context 可能还是空。修法:
  全选 batch 跑,或逐条 Cmd+Return,或全限定名 `@db.schema.stage`。
- `transaction` 不是 Snowflake 保留字,SELECT FROM transaction 直接用;
  加双引号 `"transaction"` 反而错(大小写敏感找小写表)。
- `rows` 是保留字,不能当 AS 别名,用 row_count 或 n。

**Design notes (Day 5 收获):**
- METADATA$FILENAME + METADATA$FILE_ROW_NUMBER 是 Snowflake stage 元数据,
  COPY INTO 时直接当 _source_file / _row_num 写入,完全免去 Python loader
  拼接逻辑。模板:`SELECT $1..$N, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER`
  在 13 张 csv/pipe/jsonl/fixed_width 后续表全部复用。
- _row_num 在 Postgres vs Snowflake 起算不同:Postgres 数文件物理行
  (header inclusive,1-indexed),Snowflake 数 SKIP_HEADER 后数据行
  (1-indexed)。e.g. employer_registry: Postgres 2..401, Snowflake 1..400。
  Raw 层保留各自 native;stg 层 Week 5 +/-1 对齐。
- _source_file 也不对称:Postgres 是干净 basename,Snowflake 是
  stage 全路径 + .gz 后缀。同样 stg 层规范化。
- transaction_control / member_census_control 表 Day 5 全部留空,T/HDR/TRL
  行通过 ON_ERROR=CONTINUE 跳过(或 read_rows() 自身跳)。两个 control 表
  补到 Day 6 或 Week 9。

**Next (Day 5 收尾, 5/19):**
- Step 6: t3010_ident (~84k 行) + t3010_schedule3 (~43k 行) COPY INTO
- Step 7: 全表对账(Snowflake vs Postgres 14 张表的 row count 一张表)
- Step 8: Day 5 commit + progress log
- 留两个 known issue:
  - portal_event 1.8% 差异(Day 6 用 TRY_PARSE_JSON 补)
  - 2 个 control 表空(Day 6+ 或 Week 9 补)