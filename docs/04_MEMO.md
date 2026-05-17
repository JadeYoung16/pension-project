# Pension Project — 续接到 3.6 完成,准备 Week 4 (Snowflake / dbt)

## 项目当前真实状态

3.6 end-to-end test 完成。raw_oncap layer 8 张表共 ~602k 行干净落库。
transaction checksum 工作并经故意失败 sanity-tested。
member_census checksum 延后,见 deferred 项。

## raw_oncap schema (3.6 终态)

| 表 | 行数 | 格式 |
|---|---|---|
| employer_registry | 400 | csv |
| call_log | 4,122 | csv |
| transaction | 186,865 | pipe (有 H/T,checksum 激活) |
| member_census | 100,000 | fixed_width (.DAT,checksum 延后) |
| portal_event | 59,606 (+ 18 rej malformed_json) | jsonl |
| life_event | 17,638 | pipe (无 H/T) |
| seminar_attendance | 5,816 | csv |
| email_engagement | 227,502 | csv |
| _rejected | 19 (18 portal + 1 transaction test) | (append-only audit) |
| transaction_control / member_census_control | 空 (3.6 弃用,详见决策) | |

## 已完成的子步骤

- 3.1 ~ 3.4 (略,见之前 memo)
- 3.5 ✅ 全部完成:member_census + portal_event + life_event + seminar_attendance + email_engagement
- 3.6 ✅ end-to-end test:--all 跑通 + transaction checksum + sanity test + member_census checksum 显式延后

## 锁定的设计决策 (3.6 新增)

- **`--all` 是每表独立事务**,串行 8 次 commit。raw layer 表间无 FK,
  独立性强,单表失败不影响其它表已 committed 数据。
  代码:`_db.py:105 conn.commit()` 在 `load_table` 内部。

- **`_rejected` 是 append-only 审计表**,跨 run 累积。3.5 设计意图,
  写在 `_db.py:58` 注释 "NOT truncated"。当前唯一切片维度是 `rejected_at`
  + `target_table` + `failure_reason`,长期可能要加 `load_run_id`,
  但当前不必要(优先级让位 Week 4)。

- **transaction_control / member_census_control 两张空表弃用**。
  原 3.6 任务 f 设计意图是"每次 load 写 control metadata 入库供查询审计"。
  3.6 实际决策:control 信息走 `_rejected` 现有机制即可
  (`failure_reason='control_mismatch'`,跟 `'malformed_json'` 同级)。
  好处:零新表结构、跟 portal_event 的 reject path 语义一致、 
  loader 不污染。两张空表保留在 schema 但永远不会写入,
  下次 schema cleanup 时删掉。

- **pipe_format checksum 是内容驱动**:有 H/T 启用对账,无 H/T 自动跳过。
  同一份代码同时伺候 transaction (有 H/T) 和 life_event (无 H/T)。
  这是 3.5 "内容驱动 > 位置驱动" 设计胜利的延续。

- **checksum 失败 → 写 _rejected 行,数据照 commit**。理由:
  (1) 复用现有 reject 机制零工程量;
  (2) 跟 portal_event 的 row-level reject 走同一路径,审计对称;
  (3) 数据被 commit 但 audit 行留下,下游 dbt 可按需过滤。
  代价:不像 rollback 那么严格,但对 demo 充分。

## 3.6 transaction checksum 实现细节

- `TableConfig` 加 `sum_columns: tuple[str, ...] = ()` 字段。
- transaction config 设 `sum_columns=("member_contribution", "employer_contribution")`。
- `pipe_format.read_rows` 加第三个参数 `sum_columns=()`,默认空 tuple。
- csv_format / jsonl_format 也加该参数(忽略),接口对称。
- `_db.py` 第二支调用统一传 `cfg.sum_columns`。
- pipe_format 内部:H 存 record_count,T 存 record_count + per-column sums,
  数据行边 yield 边累加 actual_count + actual_sums (Decimal),文件末尾对账。
  不一致 → yield ("reject", {...failure_reason='control_mismatch'...})。
- T 行有但 H 无、或反之 → 单边对账,不算 mismatch。
- 完全没 H/T → 早退,无任何 checksum 开销 (life_event 路径)。

## sanity test 证据

3.6 中故意改 transaction T 行的 record_count (21547 → 99999):
- reject 触发,row_num = 21550 (= 21547 data + 1 H + 1 column header + 1 T)
- failure_detail 准确:
  "H.record_count=21547 != T.record_count=99999; T.record_count=99999 != actual=21547"
- 恢复原文件后,transaction load 回到 0 rejected。
- _rejected 那行作为"checksum 真在跑"的永久 audit 证据保留。

## Deferred 项

- **member_census checksum (TRL.record_count + SHA256[:32] 对账)**:
  3.6 显式延后。理由:
  (1) 真正干净的做法是让 fixed_width_format 也读 member_census_layout.yaml
      ("loader 与 generator 共享 YAML" 是 3.1 文档化的设计意图,
      当前 TableConfig.field_positions 是硬编码,违背原意);
  (2) 路 2(继续硬编码 HDR/TRL 切片)做了不正确的妥协;
  (3) 路 3 是正解但是 scope creep,与 Week 4 优先级冲突;
  (4) transaction checksum 已经证明 reject pattern 在 control_mismatch 
      场景工作,member_census 是补对称性,不是补新知识。
  TODO 注释保留在 `fixed_width_format.py:74,77`。
  延后到独立的小项目 (可能是 Week 5 polish 或 backlog)。
  对 Week 4 Snowflake / dbt 零影响 —— dbt 只关心落库的行,不关心 load 时是否对账。
- a. cra_t3010_2023 入库 (Python loader 扩展,新 raw_external schema)
- (uci_bank_marketing 跳过 Week 4,见 Deferred 项)


- **`load_run_id` 列与 control_run 表**:不加。理由同上(优先级让位)。
  `_rejected` 当前的 `target_table + failure_reason + rejected_at` 
  对当前规模够用。如果未来 _rejected 行数到了千级,再加 load_run_id 切片。

- **H-but-no-T edge case (truncated file)**:pipe_format 当前会静默 commit。
  TODO 留在 `pipe_format.py` 顶部注释。3.6 不挡 Week 4。

## 已经讲过的概念 (3.6 新增)

- ACID atomicity 在双 COPY 场景的作用(complement 3.5 portal_event)
- Decimal 累加避免 float 精度损失 (transaction sums 用)
- 接口对称性:让所有 format 模块接同样默认参数,_db.py 一支调用搞定
- 内容驱动 vs 配置驱动 (sum_columns 是 config,有无 H/T 是内容)
- truncated SHA256(取 hexdigest[:32] = 128 bits)— 阅读时差点误认为 MD5
- "memo 是回忆,代码/数据是事实" 第二次戳到:
  3.5 memo 说 SHA256,文件里 32 hex 像 MD5,generator 真相是 truncated SHA256
- sanity test by deliberate breakage:checksum 通过和 checksum bypassed 输出一样,
  必须用故意改坏的输入证明 reject path 真在工作

## 下一步:Week 4 — Snowflake / dbt

raw_oncap layer 完整且可信。raw_external (cra_t3010 + uci_bank_marketing) 
仍未入库,需要决定走 dbt seed 还是 Python loader 扩展 — Week 4 第一个设计点。

Week 4 整体方向:
- - a. cra_t3010_2023 入库 (Python loader 扩展,新 raw_external schema)
- (uci_bank_marketing 跳过 Week 4,见 Deferred 项)
- b. Snowflake 环境 (account / warehouse / database / schema)
- c. dbt 项目初始化 + connection profile
- d. raw → staging 第一层 (rename / type cast,不做 join)
- e. staging → marts (join / aggregation 起点)

具体 Week 4 task list 留 Week 4 第一轮对话确认。