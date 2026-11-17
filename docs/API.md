# 接口

`POST /api/run`：JSON中的csv文本，省略使用样例；或multipart字段file。最大5MB。

`POST /api/m1`至`POST /api/m7`：独立运行到指定模块，JSON结构同运行接口。

`GET /api/history`：历史批次。`POST /api/review`接收id、revision和decision（通过或退回）。`GET /api/evidence.csv`提供单一证据导出。

结构错误422，版本变化409，文件过大413；错误返回code与message。所有页面可从左侧七个模块入口访问。

`GET /api/runs/<id>`读取指定批次；页面与证据CSV通过run_id查询参数绑定批次，模块导航保留该参数。

JSON请求体必须是对象，数组、标量、null、损坏JSON及错误上传字段返回400，且不运行默认样例。

## 撤销补录（M7 派生版本，本地离线）

补录不覆盖原批次：从原批次派生内容寻址的新版本，原payload、复核结论与revision保持不变。

- `POST /api/revocations`：`{run_id, standard_id, effective_date, reason?, fault_plan?}`。自然键`(run_id,standard_id,effective_date)`幂等，重复提交复用同一记录与派生版本；不带`fault_plan`的重试会清除旧故障计划并续跑。
- `GET /api/revocations?run_id=`：补录记录列表。`GET /api/revocations/<id>`单条。
- `POST /api/revocations/<id>/resume`：按`bf_journal`检查点续跑；已完成项跳过，`applied`记录为幂等空操作。
- `GET /api/batches/<root_id>/current`：当前指针、版本谱系与当前批次payload。
- `GET /api/retests?revocation_id=`（或`run_id=`）：重测去向任务。
- `POST /api/retests/<id>/disposition`：`{destination, note?}`，destination限`待重测/重测中/已重测合格/已重测不合格/停用`，非法值422。
- `GET /api/revocations/<id>/evidence`：三视角证据包JSON（原路径/当前影响/去向+续跑日志），含`bundle_sha256`与派生批次`evidence_sha256`，均可离线复算。
- `GET /api/revocations/<id>/evidence.csv`：同内容CSV导出。
- 页面：M7页`/work/7`发起补录；`/revocations?run_id=`档案列表；`/revocations/<id>`证据三视图。
- `fault_plan`仅用于演示写入中断：`{stage:"derive"|"switch", fail_after_items:n, message?}`。切换（switch）在单事务内完成，失败回滚，当前指针仍指原批次、原复核证据继续可见。所有接口不访问外部源。
