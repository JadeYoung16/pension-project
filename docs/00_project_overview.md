Pension Project — 最终设计
Last updated: 2026-05-16 (Week 3.6 完成,准备 Week 4)
Target completion: 2026-07-10 (Week 9 收尾)
1. 项目定位
目标:Analytics Engineer 求职 portfolio
核心叙事:模拟安省 non-profit / 公共部门养老金计划 (OPTrust Select 风格) 的端到端数据平台,反映 pension 行业 on-prem → cloud 迁移的混合架构
简历卖点:dbt + Snowflake + 维度建模 + 数据测试 + CI/CD + dashboard;
Python loader / Docker / Git 作为次要支撑
分析叙事:mart 层映射经典 marketing funnel 框架 (mid / lower / retention);
Week 8.5 用 UCI Bank Marketing 做独立 AB testing 扩展
职责定位:简历主线讲 Analytics Engineer 工作(Snowflake 内部 dbt + 建模 + 测试 + dashboard);
Week 1-3 的 Python loader 工作作为"懂上游"的隐藏能力,面试被问到时展开
2. 最终技术栈
已完成 (Week 1-3):
Python 3.11(generators + loaders)
Docker + Docker Compose(两容器:pension-app + pension-postgres)
PostgreSQL 16(本地 raw landing)
Git / GitHub
待引入 (Week 4-9):
Snowflake(云端 staging + marts)
dbt(dbt-postgres → dbt-snowflake)
GitHub Actions(CI/CD,Week 5 起,自动 dbt build + lint on PR)
Airflow(轻度调度,主要调 dbt run)
Power BI 或 Metabase(dashboard)
明确排除:Terraform / Data Lake / Spark / Databricks / Kafka / Kubernetes / streaming
3. 数据流架构
Synthetic Generators (Python, 8 个)
         ↓
本地 PostgreSQL: raw_oncap        ← 模拟 on-premise 落地
         ↓ (Python loader 扩展)
Snowflake: raw_oncap + raw_external
         ↓ (dbt staging)
Snowflake: stg_oncap
         ↓ (dbt marts)
Snowflake: mart_oncap             ← 业务层 / 维度模型
         里 fct_member_engagement_funnel
         ↑ 映射经典 marketing funnel 框架 (mid / lower / retention)
         ↓
Power BI / Metabase
横向贯穿:GitHub Actions CI(PR 时自动 dbt build + lint)
        Airflow(调度 dbt run)
4. raw_oncap 当前真实状态(8 表,~602k 行)
employer_registry — 400 行,csv,单文件
call_log — 4,122 行,csv,3 个月度文件
transaction — 186,865 行,pipe (H/T),checksum 已激活,sanity-tested
member_census — 100,000 行,fixed_width (.DAT),checksum 显式延后(见 §7)
portal_event — 59,606 行,jsonl,event_properties → JSONB,~0.01% reject
life_event — 17,638 行,pipe (无 H/T),内容驱动同 pipe_format
seminar_attendance — 5,816 行,csv
email_engagement — 227,502 行,csv
加 _rejected 19 行(append-only,18 portal malformed_json + 1 transaction control_mismatch sanity-test artifact)。
外加 transaction_control / member_census_control 两张空表,3.6 决策弃用(下次 schema cleanup 删掉)。
5. loader 设计哲学(锁定)
混合类型:标量列有类型,嵌套数据 → JSONB
不崩,坏数据进 _rejected:行级 reject (malformed JSON) + 文件级 reject (control_mismatch) 走同一路径
truncate-and-load:每表 8 次独立事务串行(_db.py:105 commit 在 load_table 内部)
raw 层 1:1 镜像源文件:列名不改,类型转换留给 dbt
_rejected 是 append-only 审计表:跨 run 累积,by design (_db.py:58)
format 模块统一接口:yield (tag, payload),good/reject 两 payload 都用 dict 对称
内容驱动 > 位置驱动:pipe_format 同一份代码同时伺候有 H/T (transaction) 和无 H/T (life_event)
checksum 失败 → _rejected 一行,数据照 commit:复用现有机制,零新表结构
6. 项目目录结构(终态)
pension-project/
├── Dockerfile / docker-compose.yml / requirements.txt
├── .env / .env.example / .gitignore
├── .github/workflows/           # Week 5 起,CI/CD
│   └── dbt_ci.yml               # PR 触发 dbt build + sqlfluff
├── docs/
│   ├── 00_project_overview.md
│   ├── 01_plan_design_specification.md
│   ├── 02_data_generation_plan.md
│   ├── 03_record_layouts.md
│   ├── 04_data_sourcing.md           ← Week 9 新增
│   ├── incidents/                    ← Week 9 新增
│   │   └── 2026-05-16_transaction_checksum_mismatch.md
│   └── _progress_log.md
├── upstream_simulators/         # 8 个 generators (Week 1)
│   ├── config/record_layouts/   # YAML specs (含 member_census_layout.yaml)
│   ├── generators/
│   └── shared/writers/
├── loaders/                     # Week 3 主成果
│   ├── _cli.py / __main__.py    # python -m loaders load --all
│   ├── _config.py               # TableConfig + TABLES registry
│   ├── _db.py                   # 共享 TRUNCATE + COPY + reject 路由
│   └── _formats/
│       ├── csv_format.py
│       ├── pipe_format.py       # 含 checksum 对账
│       ├── jsonl_format.py      # 含 reject 路径
│       └── fixed_width_format.py
├── sql/                         # raw_oncap DDL
├── data/
│   ├── synthetic/               # 8 个表的源文件
│   └── raw_external/            # cra_t3010 + uci_bank_marketing
├── dbt/                         # Week 4 起
│   ├── dbt_project.yml
│   ├── profiles.yml             # gitignored
│   ├── models/
│   │   ├── staging/             # stg_oncap.*
│   │   └── marts/               # dim_*, fct_*
│   ├── tests/
│   ├── seeds/
│   └── macros/
└── airflow/                     # Week 7 起
    └── dags/
        └── dbt_daily.py
7. 显式 deferred 项
member_census checksum (TRL + SHA256[:32])
原因:干净做法需让 loader 也读 member_census_layout.yaml(YAML 顶部声明的设计意图),硬编码 slice 是错误妥协,正解是 scope creep
何时做:独立小项目,可能 Week 5 polish

pipe_format H-but-no-T edge case
原因:文件截断时静默 commit,robustness 完善
何时做:3.6.5 / backlog

_rejected.load_run_id 列
原因:当前 target_table + failure_reason + rejected_at 切片够用
何时做:行数到千级再加

transaction_control / member_census_control 表
原因:3.6 决策弃用,control 信息走 _rejected
何时做:下次 schema cleanup 删掉

uci_bank_marketing 入 warehouse
原因:Week 1 设计意图是 ML benchmark 对照,不是 warehouse 资产
主要价值:Week 8.5 做 AB testing 独立扩展项目;Week 5+ ML 阶段作为 benchmark 对照
何时做:不入 warehouse,Week 8.5 / Week 5+ 时直接 pandas 读 csv

upper funnel (employer acquisition) mart
原因:数据已可支持(T3010 是 prospect universe,employer_registry 是 converted),但 Week 4-7 主线优先 member engagement;现在加字段、模型 Week 6 看精力做,避免 retrofit
何时做:Week 4 入 T3010 时给 employer_registry generator 加 acquisition 字段并重生成(~半天);Week 6 marts 阶段如时间宽裕,加 fct_employer_acquisition_funnel,变成 dual-funnel 叙事;不做也不影响主线

Databricks / Spark
原因:数据量 ~600k 行不需要分布式;加进来是堆术语
何时做:本项目完工后,2026 年 8-9 月单独做小项目展示

8. raw_external 决策(Week 4 起点)
cra_t3010_2023 → Python loader 扩展,进新 raw_external schema。Plan sponsor 是 non-profit / charity sector,通过 business_number join employer_registry 做 dim enrichment(employer 财务/规模数据);同时作为 upper funnel prospect universe(见 §7.6)
uci_bank_marketing → 不入 warehouse。Week 8.5 做独立 AB testing 扩展;Week 5+ ML 阶段直接 pandas 读 csv
9. Week 推进表 + Deadline
每天 4 小时基准。
Week 1 — 数据生成器 + 文档 + 外部数据下载 — ✅ 完成
Week 2 — Docker + Git + Postgres + 三层 schema — ✅ 完成
Week 3 — Python loader(3.0~3.6 共 7 个 sub-step)— ✅ 完成 (2026-05-16)
Week 4 — cra_t3010 入库 + employer_registry 加 acquisition 字段重生成 + _load_audit 表 + metadata 记录 + Snowflake setup + dbt 初始化 + 第一批 staging models — 目标 2026-05-23
Week 5 — dbt-snowflake + staging 完整 + marts 起点 + CI/CD 基础(GitHub Actions Tier 1)— 目标 2026-06-06
Week 7 — Airflow 调度 dbt run — 目标 2026-06-27
Week 8 — Dashboard(Power BI 或 Metabase)— 目标 2026-07-04
Week 8.5 — AB Testing Extension(UCI Bank Marketing 独立分析)— 目标 2026-07-08
Week 9 — README + project case study + screencast demo + 
  Data Sourcing Document + Incident Post-mortem — 目标 2026-07-10
Final deadline: 2026-07-10 (从 5/16 起 ~55 天)
10. 守时原则(避免超期)
每个 Week 设硬截止,卡超 1.5 倍预算就标 TODO 跳过,推进下一步
不追求"完美 dbt 项目",追求"能跑通 + 能讲故事"
Buffer 不能挪用,留给 Week 9 收尾 polish
学习别陷进去,Snowflake / dbt / Airflow 够用就停
每周末写 progress note 到 docs/_progress_log.md(记录:做了啥 / 卡在哪 / 下周起点)
11. 已踩坑、写进流程的教训
"备忘录是回忆,代码是事实" — 每次开干前 cat 当前代码,不照记忆走。Week 3 多次救场(pipe_format 无 H/T 那次零改动、TRL 那个 SHA256 vs MD5 误会)
rule of three / 抽象由痛点定义 — 不预先搭脚手架,等第二第三个类似需求出现才抽象(_db.py / _formats/ 都是这样诞生)
checksum 必须用故意改坏的输入 sanity-test — checksum 通过和 checksum bypassed 输出一样,只能用 deliberate breakage 证明 reject path 真在工作
设计决策列全再动手 — Week 3.5 末期的接口 churn 源于"边写边发现新选项",3.6 起的流程是先列所有设计点 → 拍板 → 写代码
scope creep 的识别 — "既然在这了顺手"是经典推迟陷阱(member_census checksum 路 3 / 当前加 Databricks 都是这类)。延后比走错的妥协路便宜
现在埋数据基础 vs 未来 retrofit — Week 4 给 employer_registry 加 acquisition 字段就是这条原则:数据现在加成本极低,未来 retrofit 翻倍
职责定位明确比技术广度重要 — Analytics Engineer 简历从 warehouse raw 讲起,上游 loader 是加分项不是核心。技术堆砌(如把 Databricks 强塞)是 Junior 思维

