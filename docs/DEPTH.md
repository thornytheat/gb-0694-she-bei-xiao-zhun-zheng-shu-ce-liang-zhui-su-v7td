# 深度登记 设备校准证书与测量追溯

- 规模：中型
- 使用者与工作流：检验机构质量员，合并仪器使用与校准证书，裁决测量是否在有效可追溯链内。
- 核心规则：证书有效期与量程双约束；参考标准也须在校准时有效，证书撤销向下游传播并检测环。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 证书接收 | 运行证书接收并复核证据 | `POST /api/m1`；`/work/1` | `app/modules/m1_receiving/rules.py` | `tests/test_m1.py` |
| M2 设备别名 | 运行设备别名并复核证据 | `POST /api/m2`；`/work/2` | `app/modules/m2_identity/rules.py` | `tests/test_m2.py` |
| M3 有效区间 | 运行有效区间并复核证据 | `POST /api/m3`；`/work/3` | `app/modules/m3_validity/rules.py` | `tests/test_m3.py` |
| M4 量程匹配 | 运行量程匹配并复核证据 | `POST /api/m4`；`/work/4` | `app/modules/m4_ranges/rules.py` | `tests/test_m4.py` |
| M5 溯源链路 | 运行溯源链路并复核证据 | `POST /api/m5`；`/work/5` | `app/modules/m5_trace/rules.py` | `tests/test_m5.py` |
| M6 测量裁决 | 运行测量裁决并复核证据 | `POST /api/m6`；`/work/6` | `app/modules/m6_verdict/rules.py` | `tests/test_m6.py` |
| M7 撤销复核 | 运行撤销复核、补录标准器撤销并复核证据 | `POST /api/m7`、`POST /api/revocations`；`/work/7`、`/revocations/<id>` | `app/modules/m7_revocation/rules.py`、`app/backfill/` | `tests/test_m7.py`、`tests/test_backfill.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码证书 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m1_receiving/rules.py` | `tests/test_m1.py::test_legacy_chinese` |
| TRAP-07 | 空值测量 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_missing_isolated` |
| TRAP-08 | 设备编码保形 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_device_code_preserved` |
| TRAP-14 | 定义冲突 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_conflict_certificate_flag` |
| TRAP-20 | 溯源依赖环 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m5_trace/rules.py` | `tests/test_m5.py::test_reference_cycle` |
| TRAP-22 | 设备别名 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_alias_order_independent` |
| TRAP-23 | 失效日边界 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m3_validity/rules.py` | `tests/test_m3.py::test_expiry_endpoint` |
| TRAP-25 | 多证书重叠 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m3_validity/rules.py` | `tests/test_m3.py::test_overlapping_certificates` |
| TRAP-30 | 撤销补录覆盖复核证据 | 直接改写原批次，已复核结论与原路径被毁 | 从原批次派生内容寻址新版本，原payload/revision/decision不动 | `app/backfill/engine.py` | `tests/test_backfill.py::test_original_payload_is_not_mutated` |
| TRAP-31 | 生效日边界重算 | 全量拒用或全量维持，忽略生效日 | `measured_at < 生效日`维持原判断，`>= 生效日`的下游才拒用重测 | `app/backfill/engine.py` | `tests/test_backfill.py::test_effective_date_is_closed_boundary` |
| TRAP-32 | 补录重试产生新版本 | 每次重试新建派生批次，证据分叉 | 自然键+确定性派生ID，重试只复用原记录与原版本 | `app/backfill/service.py` | `tests/test_backfill.py::test_retry_reuses_same_record_and_derived_version` |
| TRAP-33 | 切换失败后档案指向失效标准器 | 先切指针后写派生，失败即悬空 | 切换与写入在单事务内，失败回滚，当前指针仍指原批次 | `app/backfill/store.py` | `tests/test_backfill.py::test_switch_failure_leaves_original_evidence_visible` |
| TRAP-34 | 写入中断不可续跑 | 崩溃后从头重跑或丢进度 | `bf_journal`逐项检查点，blocked留痕、续跑跳过已完成项 | `app/backfill/service.py` | `tests/test_backfill.py::test_derive_fault_is_resumable_and_keeps_current_pointer` |

## 对账规则

输入记录 = 采信记录 + 隔离记录 + 相同行重复。重复表头与空行单独记数。业务合计按阶段中的守恒或差值列复核。运行清单有原文SHA256、规则版本与耗时；相同规则版本下同文重复提交复用批次。

## 已知不覆盖

部署为本地单用户工具，不连接外部上游系统。CSV单文件5MB及一万条业务记录上限；不推断未提供的未知数据。撤销补录同样离线运行，标准器必须已存在于目标批次，生效日与影响范围仅依据本地溯源结构计算，不接外部数据源。
