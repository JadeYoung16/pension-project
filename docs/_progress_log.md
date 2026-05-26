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


  ## 2026-05-19 — Week 4 Day 5(完成)

承接昨天下半段,今早收尾。

**Done(Day 5 收尾段):**
- Step 6: t3010_ident (83,969) + t3010_schedule3 (43,151) COPY INTO 通
- Step 7: 全表对账完成。14 张表 Postgres vs Snowflake 一致,
  差异全部在已知项:
  - portal_event Δ = -1,069 行(1.8%, Day 6 用 TRY_PARSE_JSON 补)
  - _rejected / _load_audit Snowflake 端空(设计选择,Snowflake 用内置
    INFORMATION_SCHEMA.COPY_HISTORY + ACCOUNT_USAGE.COPY_HISTORY 顶替)
  - member_census_control / transaction_control 两边都空(Day 6+ 补 control
    数据 parsing,或者 Week 9 polish 一起补)

**数据完整度:Postgres 956,624 行 / Snowflake 955,524 行 / 99.88%**

**Snowflake side 语法/版本踩坑(Day 5 末段补充):**
- `(FILE_FORMAT => (TYPE = CSV, FIELD_DELIMITER = ',', ...))` inline 写法
  在 stage SELECT 上下文不稳定;命名 file format 引用更稳:
  `(FILE_FORMAT => 'PENSION_DEV.RAW_ONCAP.CSV_FORMAT')`。
  COPY INTO 里则用 `FILE_FORMAT = (FORMAT_NAME = CSV_FORMAT)`,语法略不同。
- stage 跨 schema 引用必须用全限定名 `@PENSION_DEV.RAW_ONCAP.LOAD_STAGE/`。

**Day 5 完整 sub-step 状态:**
- [x] Step 1: stage + 3 file formats
- [x] Step 2: Python connector 测连接
- [x] Step 3: PUT 146 文件到 stage(含 member_census 2 个预处理 csv)
- [x] Step 4: employer_registry COPY 模板验证
- [x] Step 4b: 6 张表 COPY(portal partial)
- [x] Step 5: member_census 预处理 + COPY
- [x] Step 6: t3010 两表 COPY
- [x] Step 7: 全表对账
- [ ] Step 8: 此处 commit(下一步动作)

**Buffer 状态:**
- 原计划 Day 5 = 5/18,实际 5/17 上半段 + 5/18 下半段 + 5/19 收尾段 ≈ 2 天工作量
- Buffer 已用掉 +1 天,从 +2 天降到 +1 天
- Week 4 整体仍提前 1 天(原计划 Day 7 = 5/23,理论 5/22 能完成)

**Open carries to Day 6:**
1. portal_event TRY_PARSE_JSON 重做(行级 reject,把 1,069 行找回来)
2. (低优)member_census_control + transaction_control 数据(改 read_rows
   返回 HDR/TRL,或本地预处理生 control csv)
3. 决定 Day 6 起做什么:
   - 选项 A: 先补 portal 完整性 + 2 control 表,然后 dbt init
   - 选项 B: 直接 dbt init,portal 1.8% 和 control 表等 Week 9 polish
   倾向 B —— raw 层 99.88% 完整,主线推进比补漏更重要,
   Week 5 dbt staging 起跑后下游 KPI 受影响极小。


   ## 2026-05-20 - Week 4 Day 6 (dbt scaffold + first staging models)

按计划 Day 6 = 5/20。预估 4-5h, 实际跨越 5/20+5/21 两天 ~6h. Buffer
+0.7 天降到 +0.2 天, 但学到的东西在三个方向都深 (dbt setup / staging
design / data quality discovery), 值得.

**Done:**
- Step 1: dbt-core 1.11.11 + dbt-snowflake 1.11.5 装上. requirements.txt
  pin 哲学重写: == for app-direct deps, range for foundational libs.
- Step 2: profiles.yml committed at /app/dbt/profiles.yml with env_var
  references, secrets stay in .env. DBT_PROFILES_DIR injected via
  docker-compose.
- Step 3: dbt debug All checks passed.
- Step 4: dbt_project.yml layered config (staging.oncap -> stg_oncap view,
  staging.external -> stg_external view, marts.oncap -> mart_oncap table).
  generate_schema_name macro override so +schema: foo lands models in
  foo directly (not target.schema_foo).
- Step 5: _sources.yml declares 14 sources with descriptions including
  known design caveats from Days 5.
- Step 6: stg_oncap__employer_registry (400 rows). 4 iterations v1->v4
  to converge on A/B/C case normalization principle + pay_frequency
  code-to-word case mapping.
- Step 7: _properties.yml + 11 tests. PASS=11 first try thanks to
  v3->v4 raw-data verification cycle.
- Step 8a: stg_oncap__call_log (4,122 rows). v1 one-shot using the
  template; 8 tests PASS.
- Step 8b: stg_oncap__member_census (50,000 rows after snapshot dedup).
  Most complex of three.
- Step 9: 3 commits (infrastructure / staging models / progress log).

**Snowflake state at end of Day 6:**
- stg_oncap.stg_oncap__employer_registry (view, 400)
- stg_oncap.stg_oncap__call_log (view, 4,122)
- stg_oncap.stg_oncap__member_census (view, 50,000)
- raw layer untouched (14 source tables intact)

**Staging design principles established (will reuse Week 5):**

A. Case normalization A/B/C taxonomy:
   A: enum text -> lower
   A': cryptic short codes -> case map to full words (no else,
       defensive against upstream new codes)
   B: numeric codes -> preserve (lower is no-op)
   C: display free text -> preserve (lower destroys meaning)
   Cryptic codes lacking universal interpretation -> preserved,
   code-to-label translation deferred to dim_* mart layer.

B. PII metadata pattern: contains_pii + pii_type + sensitivity tier
   in config.meta. Programmatic identification for downstream
   masking/RBAC.

C. Grain documented in model header. Composite PKs use singular
   tests until dbt-utils added.

D. NULL semantics: preserve legitimate business NULLs (termination_date,
   csat_score, member_since_date). Document each in yaml description.
   Defensive case statements (no else) make schema drift visible.

**dbt test as raw-data quality discovery (4 issues caught):**
1. sex_code has 3 values (1/2/9), not 2. StatCan census codeset.
2. status_code has 5 values (a/d/r/s/t), not 2.
3. member_census raw is monthly snapshot data (100k = 50k x 2 months).
   member_id alone is not unique.
4. 4 enum fields show Phase-1 generator UPPERCASE vs Phase-2 lowercase.

Each was a fail-then-fix cycle: my yaml guessed values, dbt test failed,
data DISTINCT query revealed truth, yaml updated to actual. This is dbt
test working as designed - upstream data shape forced into review at
staging rather than silently propagated to mart.

**Stuck / lessons:**
- pip resolver deadlock: Day 5 ==3.12.3 on snowflake-connector-python
  blocked Day 6 dbt-snowflake which requires >=4.2.0. requirements.txt
  needed full pin philosophy rewrite. Lesson: app-direct libs == ;
  foundational libs (HTTP/crypto/pyarrow) range.
- Snowflake warehouse 5-layer context precedence (USE > worksheet >
  connection > USER default > ROLE default). .env still had
  COMPUTE_WH from earlier setup, didn't match Day 4 PENSION_WH design
  intent. Fixed: .env single source of truth must reflect design.
- docker compose build cache: new apt packages (git for dbt) require
  --no-cache or Dockerfile layer changes don't take effect.
- YAML deprecation: dbt 1.10+ moved column meta: into config.meta:.
  Functional difference: nothing yet; warning compels fix to stay
  spec-current. Caught accidentally inserting prose-style "<- new
  location" annotations from mentor message into yaml file, breaking
  parser. Lesson: code blocks shared in writing must be paste-ready;
  inline annotations belong in surrounding prose, not embedded.

**Buffer state:**
- Day 6 originally estimated 4-5h, actual 6h across two calendar days.
- Buffer +0.7 -> +0.2.
- Week 4 nominal end Day 7 = 5/23, current trajectory 5/22 still
  meeting target.

**Next (Day 7, 5/22-23):**
- 5 remaining oncap staging models (seminar/email/transaction/
  life_event/portal_event)
- 2 external staging models (t3010_ident, t3010_schedule3)
- dbt-utils package install for composite unique / accepted_range
- Week 4 retro / status notes for Week 5 entry

1. transaction_id 3 行重复 (generator bug)

同一 id, 不同 pensionable_earnings
处理: severity=warn + error_if 10 degradation threshold
Backlog: Week 9 polish 修 generator

2. pay_period_start 2% NULL (generator artifact)

跨所有 pay_frequency 均匀 ~2% NULL
处理: severity=warn + error_if 5000 degradation threshold
Backlog: Week 9 polish 让 generator 永不 NULL

3. contribution_type 单值 + buyback_reference_id 全 NULL (generator gap)

Generator 没生成 BBK contribution type
life_event 有 8,254 BBK_INSTALLMENT_PAY 但 transaction 0 个 BBK
Backlog: Week 9 polish 生成 BBK transactions 闭合 lifecycle


## 2026-05-23 - Week 4 Day 7 (dbt-utils + 5 more staging models)

按计划 Day 7 = 5/23。预估 4-5h, 实际跨 5/23+5/25 ~5h. Buffer +0.2
保持。Week 4 主线收口。

**Done:**
- Step 1: dbt-utils 1.3.x package installed. Replaced Day 6 singular
  composite-unique test with dbt_utils.unique_combination_of_columns.
  Added dbt_utils.accepted_range to csat_score (1-5).
- Step 2-6: 5 oncap staging models, ~485k raw rows total.
- Step 7: 2 external staging models (t3010_ident, t3010_schedule3).
- Step 8: Week 4 retro + Week 5 entry notes (this commit).
- Step 9: 3 commits.

**Snowflake state at end of Day 7:**
- 8 staging views (6 oncap + 2 external)
- 117 data tests, PASS=114 WARN=3 ERROR=0

**3 documented data quality issues (warn-tracked):**

1. transaction_id has 3 duplicates / 186,865 (0.0016%)
   - Generator bug: same id used for 2 records with different earnings
   - Configured: severity=warn, error_if >= 10
   - Backlog: Week 9 polish generator fix

2. pay_period_start is 2% NULL (3,759 / 186,865)
   - Random across all pay_frequency values
   - Configured: severity=warn, error_if >= 5000
   - Backlog: Week 9 polish + mart-layer COALESCE derivation

3. t3010_schedule3 has 8 orphan BNs (not in t3010_ident)
   - CRA data sync timing issue, 0.02% impact
   - Configured: severity=warn, error_if >= 100
   - Backlog: Week 9 polish + cra_t3010 loader reconciliation

**Staging design patterns established (reused across all 8 models):**

A. Case normalization A/B/C taxonomy:
   - A: enum text -> lower
   - A': cryptic short codes -> case map to full words (no else)
   - B: numeric codes -> preserve
   - C: display free text -> preserve

B. PII metadata pattern: config.meta with contains_pii / pii_type /
   sensitivity tags (member_census + portal_event)

C. Grain explicit in description, validated by unique tests:
   - Simple PK: single-column unique
   - Composite PK: dbt_utils.unique_combination_of_columns

D. Conditional NULL semantics: legitimate business NULLs preserved
   and documented per-column (life_event buyback columns,
   t3010_schedule3 line items)

E. SLA-based test severity:
   - Hard error (default) for invariants
   - Warn + error_if threshold for known generator bugs

**dbt-utils integration:**
- unique_combination_of_columns: composite PK validation
  (member_census, t3010_schedule3)
- accepted_range: numeric bounds (csat_score 1-5,
  transaction contributions >= 0)

**Stuck / lessons:**
- YAML inline annotations broke dbt parser. Mentor message included
  prose-style "<- new location" markers that got pasted into yaml file.
  Lesson: code blocks must be paste-ready; comments use yaml `#` syntax.
- dbt selector syntax confusion. `--select stg_external` didn't work;
  correct is `--select path:models/staging/external` or wildcard
  `--select stg_external__*`.
- test-before-run produces silent ERROR cascade ("Object does not
  exist"). Need to run model first then test. Order matters.
- portal_event JSON: VARIANT field has variable schema per event_type.
  Decision: preserve VARIANT in staging, flatten per-event in mart.
- T3010 schedule3 column names are numeric (300, 305, ...). Required
  rename + cast strategy (line_NNN, VARCHAR -> NUMBER).
- Category dual-format ('30' vs '0030') in t3010_ident solved with
  ltrim — format normalization not business rule.

**Buffer state:**
- Day 7 estimated 4-5h, actual ~5h (across 5/23 + 5/25 due to weekend).
- Buffer +0.2 -> +0.0.
- Week 4 nominal end Day 7 = 5/23, actual completion 5/25.
- Net Week 4 timeline: on schedule.

**Next (Week 5):**
- Macro for pay_frequency case mapping (DRY refactor)
- Marts layer planning (dim_employer / dim_member / dim_charity /
  fct_contribution / fct_engagement / fct_portal_session)
- Possible Snowflake clustering keys for large tables


## 2026-05-26 — Week 5 Day 1 (pay_frequency_label macro refactor)

按计划 Week 5 Day 1 = 5/26. 预估 1-2h, 实际 ~1.5h. Buffer 保持 +0.2.
Week 5 第一个 DRY refactor; mart 层工作的基础设施热身.

**Done:**
- Step 1-2: 现状审查 + 4 个设计点拍板 (signature / case normalization /
  unknown value handling / file path). 全选 (a): 接列名参数 / 内置 lower() /
  无 else 返回 NULL / 扁平 macros/ 目录.
- Step 3: macros/pay_frequency_label.sql 创建. 32 行 (含 25 行顶部注释).
  dbt parse 通过.
- Step 4: stg_oncap__employer_registry refactor. 6 行 case -> 1 行 macro call.
  dbt compile 验证 SQL 等价.
- Step 5: stg_oncap__transaction refactor. 同上.
- Step 6: dbt run -s 两个 staging, 2 of 2 OK.
- Step 7: dbt test 全项目 PASS=114 WARN=3 ERROR=0 TOTAL=117 — 跟 refactor
  前 baseline 完全等价. 纯重构验证通过.

**Latent bug fixed during refactor:**
- stg_oncap__transaction's case 缺少 employer_registry 有的 defensive
  lower(). transaction generator 当前只写 UPPERCASE 所以不 breaking,
  但若 generator 改 lowercase (像 employer phase-1->phase-2 那样) 会
  silent null-out 所有 pay_frequency. Macro 内置 lower() 把 case
  assumption 集中到一处, 所有 caller 自动获得防御.

**Macro design pattern established (reuse for Week 5+ macros):**

A. Signature: 接列名字符串 (跟 dbt_utils 惯例对齐)
B. 顶部注释承诺 4 件事: 行为 / 设计意图 / 测试建议 / 现有 callers
C. 防御性归一化 (lower() / coalesce() / trim()) 内置 macro 体,
   把"输入格式假设"集中管理而不是 caller 各自处理
D. 验证三步: dbt parse (语法) -> dbt compile (展开) -> dbt run + test (运行)

**Stuck / lessons:**
- Compiled SQL whitespace 略丑 (Jinja whitespace control 没用 {%- -%}).
  决定不修 — Snowflake 不在乎 indent, caller 源文件优美比 compiled 优美
  重要, whitespace control 容易过度调.
- 发现新 deprecation warnings (dbt 1.10+ syntax 变化):
  - MissingArgumentsPropertyInGenericTestDeprecation: 47 occurrences
  - PropertyMovedToConfigDeprecation: 1 occurrence
  - 47 个 generic test (relationships / not_null / accepted_values) yaml
    要从 top-level args 改成 arguments: 子键
  - 不混入 macro refactor commit. Backlog: Week 5 Day 7 retro cleanup.

**Buffer state:**
- Day 1 预估 1-2h, 实际 1.5h. 在轨道.
- Week 5 整体仍按 7-day plan.

**Next (Day 2-3, 5/27-5/28):**
- Marts 架构决策 — Kimball star vs Inmon 3NF
- Surrogate key 策略 — dbt_utils.generate_surrogate_key vs natural key
- Materialization 策略 — dim_* table / fct_* incremental
- 设计 dim/fct schema layout: dim_employer, dim_member, dim_charity,
  fct_email_engagement, fct_transaction (tentative list)

**Backlog updates:**
- [NEW] Week 5 Day 7: dbt yaml deprecation cleanup
  (MissingArgumentsPropertyInGenericTest x47 + PropertyMovedToConfig x1)
- [REMOVED] pay_frequency_code -> full word case mapping (DRY) ← done today