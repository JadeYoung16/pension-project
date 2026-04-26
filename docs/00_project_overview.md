# Pension Project — Overview

> 项目事实层文档。每次开新对话先读此文件，避免不同对话里设计漂移。
> Last updated: Week 2 end (Apr 25, 2026)

## 1. 项目目标

OnCap 养老金数据 ELT 项目，作为：
- DataTalksClub Data Engineering Zoomcamp 课程项目
- 求职 Analytics Engineer 岗位的 portfolio
- 模拟真实 pension 行业从 on-premise 向 cloud 迁移的混合架构

## 2. 角色定位

目标岗位：**Analytics Engineer (AE)**
- 核心能力栈：SQL + dbt + warehouse 建模 + dashboard
- 次要能力：Python loader、orchestration、Docker、Git
- 了解但不深做：Terraform、IaC、Data Lake、云架构（面试可讲概念）

## 3. 技术栈最终方案（方案 A2：本地 + 云混合）

### 已完成（Week 1-2）
- **Git/GitHub**: `git@github.com:JadeYoung16/pension-project.git`
- **Docker + Docker Compose**: 本地开发环境
- **PostgreSQL 16**: 本地数据库（dev / staging / raw landing）
- **Python 3.11**: generators、loaders、scripts
- **8 个合成数据 generators** (member, transaction, employer, life_event, 
  call_log, email_engagement, portal_event, seminar)

### 待引入
- **Snowflake**: 云端 production warehouse（free trial）
- **dbt (dbt-postgres + dbt-snowflake)**: 数据建模和转换
- **Airflow**: 轻度调度（主要调 dbt run）
- **Power BI 或 Metabase**: 最终 dashboard 展示

### 不做（明确排除，避免 scope creep）
- ❌ Terraform / IaC
- ❌ ADLS Gen2 / Data Lake
- ❌ Microsoft Fabric
- ❌ Spark / Databricks
- ❌ Kafka / 流处理
- ❌ Kubernetes

## 4. 数据流架构
[Synthetic Data Generators (Python)]
↓
[本地 PostgreSQL: raw schema]   ← 模拟 on-premise 落地
↓ (Python loader)
[Snowflake: raw schema]          ← 云端 ingest
↓ (dbt staging models)
[Snowflake: staging schema]
↓ (dbt marts models)
[Snowflake: marts schema]        ← 业务层 / 维度模型
↓
[Power BI / Metabase Dashboard]

**面试讲法**："本地 Postgres 模拟 on-premise，Snowflake 是云端目标。
这反映了 pension 行业当前从本地向云迁移的真实状态。"

## 5. 目录结构（当前）
pension-project/
├── Dockerfile                    # Python app 容器
├── docker-compose.yml            # app + postgres orchestration
├── requirements.txt              # Python deps
├── .env / .env.example           # secrets (gitignored)
├── .gitignore / .dockerignore
├── docs/
│   ├── 00_project_overview.md    # ← 本文件，事实层
│   ├── 01_plan_design_specification.md
│   ├── 02_data_generation_plan.md
│   └── 03_record_layouts.md
├── upstream_simulators/          # 合成数据 generators (Week 1)
│   ├── config/
│   ├── generators/
│   ├── shared/
│   └── run_all.py
├── downloaders/                  # 外部数据下载 (CRA T3010, UCI)
├── data/                         # gitignored, 161MB+ 生成数据
└── check_data.py

### 待添加目录（Week 3+）
├── loaders/                      # Postgres → Snowflake loader scripts
├── dbt/                          # dbt project (models, tests, macros)
├── airflow/                      # DAG definitions
└── dashboards/                   # Power BI / Metabase 配置

## 6. 周进度规划（粗略）

| Week | 主题 | 状态 |
|---|---|---|
| 1 | 数据生成器骨架、文档 | ✅ 完成 |
| 2 | 容器化环境、Git 仓库 | ✅ 完成 |
| 3 | 在容器里跑 generators，Postgres schema 设计，loader 把数据装入本地 Postgres | 📍 下次开始 |
| 4 | Snowflake 账号、dbt 初始化（dbt-postgres）、第一批 staging models | 待 |
| 5 | dbt-snowflake，Postgres → Snowflake loader | 待 |
| 6 | dbt marts (dimensional model: dim_member, fact_transaction 等) | 待 |
| 7 | Airflow 调度 dbt run | 待 |
| 8 | Dashboard | 待 |
| 9 | 完善文档、写 README、写求职用的 project case study | 待 |

## 7. 当前未决事项

- [ ] Postgres schema 命名约定（raw / staging / marts？还是别的）
- [ ] Snowflake 账号什么时候开（建议 Week 4 再开，避免 trial 时间浪费）
- [ ] Dashboard 选 Power BI 还是 Metabase（Week 8 再决定）
- [ ] 是否在容器里加 Airflow service（Week 7 再决定）

## 8. 求职 / 简历角度的关键讲法

- **岗位定位**：Analytics Engineer（不是 Data Engineer）
- **核心卖点**：dbt 深度、SQL 建模、维度建模、数据测试与文档
- **次要卖点**：Docker 容器化、本地+云混合架构、合成数据生成
- **诚实表达**：Terraform / IaC / Spark 等"了解概念，未在生产实操"
- **数据敏感性**：面试如被问"pension 真实数据上云怎么办"——脱敏 / 加密 / dedicated tenant

## 9. 下次对话开头模板

继续 pension-project Week 3 工作。请先读 docs/00_project_overview.md
熟悉项目背景和已定方案，然后我们开始：在容器里跑 generators、
设计 Postgres schema、写 loader 把数据装入本地 Postgres。