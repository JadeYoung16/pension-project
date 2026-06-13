"""
pension_pipeline — Week 7, Step B：第一条朴素线性 DAG。

编排纯 Snowflake 的 load + transform 链：
    put_files -> run_copy -> dbt_run -> dbt_test

设计决策（见 docs/_marts_design.md / Week 7 quiz）：
  - A-1：Airflow 保持 dumb。每个 task 都是 BashOperator，靠挂进来的 host
    socket `docker exec` 进 pension-app 容器——dbt、loaders、Snowflake key-pair
    全在那儿，airflow 自己什么都不装。
  - schedule=None：只手动触发（第一条 DAG、调试期；数据非定时，我们确认就位才点跑）。
  - catchup=False + 固定过去的 start_date：Airflow catchup 雪崩的护身符。
  - 线性依赖：每步消费上一步的产物 -> 硬串行。
  - retries=2：Astronomer 对 dbt task 的最低建议；四个 task 都足够幂等可安全重跑
    （put 覆盖上传 / COPY 靠 load history / dbt create-or-replace + delete+insert）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG                                    # Airflow 3 路径
from airflow.providers.standard.operators.bash import BashOperator  # 已挪进 standard provider

# 用 container 名（不是 compose service 名）——裸 docker exec 按 container 名
# 在 host daemon 上直接定位，不需要任何 compose 上下文。
APP = "pension-app"

# pension-app 容器内的路径：
#   项目根   -> /app                  （loaders 以 `python -m ...` 跑，cwd 要在根）
#   dbt 项目 -> /app/dbt/pension_dwh  （dbt run/test 的 cwd）
PROJECT_DIR = "/app"
DBT_DIR = "/app/dbt/pension_dwh"

default_args = {
    "retries": 2,                          # 四个 task 统一 2 次
    "retry_delay": timedelta(minutes=1),   # 失败后隔 1 分钟再试
}

with DAG(
    dag_id="pension_pipeline",
    description="Snowflake load + dbt transform (naive linear, Week 7)",
    schedule=None,                         # 手动触发，不自动跑
    start_date=datetime(2026, 6, 1),       # 固定过去日期，绝不用 datetime.now()
    catchup=False,                         # 绝不补跑历史区间
    default_args=default_args,
    tags=["pension", "week7", "naive"],
) as dag:

    put_files = BashOperator(
        task_id="put_files",
        bash_command=(
            f"docker exec -w {PROJECT_DIR} {APP} "
            "python -m loaders.snowflake.put_files"
        ),
    )

    run_copy = BashOperator(
        task_id="run_copy",
        bash_command=(
            f"docker exec -w {PROJECT_DIR} {APP} "
            "python -m loaders.snowflake.run_copy"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"docker exec -w {DBT_DIR} {APP} dbt run",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"docker exec -w {DBT_DIR} {APP} dbt test",
    )

    # 依赖：纯线性。每条边都是"下游消费上游产物"——真串行,无可并行对。
    put_files >> run_copy >> dbt_run >> dbt_test