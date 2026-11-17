# 数据定义

证书有效期与量程双约束；参考标准也须在校准时有效，证书撤销向下游传播并检测环。

输入字段：cert, device, alias, parent, valid_from, valid_to, minimum, maximum, unit, revoked, measured_at, value, measure_unit, version。所有ID按字符串保留；空字符串、NULL、N/A、未知与“-”视为缺失，不能当作数值零。数值使用Decimal，输出为十进制字符串。重复业务键相同内容计重复，内容冲突隔离或按明确修订号裁决，不按文件顺序盲目覆盖。

每条证据有原始行号，隔离记录有原因码及原值。时间区间使用半开边界；日期定义在各模块规则内显式声明。输入表头可调序，不得缺列或重复；中文旧编码可上传。规则版本存入运行清单，重跑使用原始文件内容摘要与规则版本共同确定幂等键。复核使用revision乐观锁，陈旧提交返回409。

校准电压量程闭区间[min,max]，证书日期为半开[valid_from,valid_to)。父证书需在子证书生效日有效；撤销按追溯性撤销处理，所有下游测量拒用。同编号证书定义冲突会使其及下游失去证明力。样例是电压仪器，未处理非线性量程和不确定度传播。

## 撤销补录派生

补录是对已存批次的离线派生，不修改原批次任何字段。日期边界为闭区间：`measured_at < effective_date`维持原判断；`measured_at >= effective_date`且证书结构上位于撤销标准器下游（`descendants`）时，M5链置`BACKFILL_REVOKED`，M6裁决在原原因码后追加该码并判拒用，同时生成一条重测任务。派生批次manifest记录`derived_from`、`lineage_root`、`backfill`（撤销标准器、生效日、影响证书、重测数）。

SQLite补录表：`bf_batch_versions`（版本谱系，root/parent/seq）、`bf_batch_current`（root→当前指针）、`bf_revocations`（自然键唯一，含status/fault_plan/error）、`bf_journal`（按`(revocation_id,stage,item_key)`的检查点，blocked行在续跑后保留，另记resumed-done）、`bf_retests`（去向任务，目标键幂等）、`bf_audit`（事件流）。证据哈希对除manifest及存储层字段（decision/revision/reused）外的payload做规范化JSON的SHA256；证据包另有`bundle_sha256`。全部数据来自本地CSV与SQLite，不接外部源。
