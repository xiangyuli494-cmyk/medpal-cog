# W2 三项 MANUAL 执行单（11/23 审核修订）

> 本单用于采集实际证据，不改写 11/15 的验收历史。11/15 本机虚拟化故障；11/17 已恢复，
> 11/18 实际会话记录在 T1 的 #37，尚未合入本分支。只读采集结果默认写入被忽略的 tmp/evidence。

## 1 采集与判定

```bash
python tools/w2_manual_evidence.py --m3-transcript tmp/actual-answer.txt
```

| 项 | 自动检查 | 限制 |
| --- | --- | --- |
| M-1 | docker ps 返回运行容器至少 13 个 | 容器数不证明服务健康 |
| M-2 | 容器内 initialize 退出码为零，JSON-RPC 的 serverInfo.name 为 medpal-cog | 宿主机返回只作诊断，不能替代容器成功；容器镜像拉取失败也记 FAIL |
| M-3 | 控制台 HTTP 200/302/307，真实回答最后三行依次为科室、检查项、完整率；内容非空，完整率为 0.00—1.00 | 自动检查不能证明控制台十工具或回答来源，必须另做人工核对 |

## 2 M-3 人工核对

1. 在 Nexent 控制台核对工具恰好为契约中的十个，保存截图，不只看服务端注册数。
2. 实际提问，保存本次最终回答全文到 tmp/actual-answer.txt，并记录会话/trace 标识和时间。
3. 核对回答及其引用属于本次执行，数值来自实际 trace_write 返回，不复制文档样例。
4. 完成人工核对后，才在同一命令追加 `--m3-reviewed`。该参数是人工确认记录，不是自动验证。
   未核对或只有格式示例时不得设置，M-3 会保留 FAIL。

脚本只做格式、可达性和人工确认的留痕，不验证科室建议的临床正确性，也不能证明截图真伪。
`--skip-m3` 将 M-3 记为未跑，退出码仍非零，不伪装全通过。

## 3 归档

默认生成 tmp/evidence/W2-manual-时间戳.md 和同名 JSON；支持 --out-dir 指向仓库外目录。
先核对原始输出、运行时间和数据来源，再选择具体文件归档：

```bash
python tools/w2_manual_evidence.py --m3-transcript tmp/actual-answer.txt --m3-reviewed
# 下列文件名替换为本次实际生成的时间戳。不要复制样例结果。
mkdir -p docs/handoff/evidence
cp tmp/evidence/W2-manual-YYYYMMDD-HHMM.md docs/handoff/evidence/
cp tmp/evidence/W2-manual-YYYYMMDD-HHMM.json docs/handoff/evidence/
```

以上复制命令是 Bash 示例，PowerShell 用 New-Item / Copy-Item；源目录与目标目录不同。
本轮留本地审阅，提交和推送另按用户授权及 PR 流程执行。

## 4 故障与验收关系

- 容器初始化超时：检查 Docker、curl 镜像及宿主 MCP；宿主机成功只能协助排错，不能把 M-2 改为 PASS。
- 控制台无响应：恢复 Nexent 后重新采集，不以历史记录替代本次运行。
- 三行无效：检查真实输出与 prompt，禁止手填一个能过格式检查的答案。
- 三项 MANUAL 不参与 acceptance 的机械 PASS/FAIL 总数，但验收仍需要其实际证据。
- 历史 W2 的三项统一为「T1 已认领、截至 11/15 未验收」；后续证据按实际日期归档，不倒填为 W2 已完成。
