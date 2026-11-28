# v1.0 封版材料核对表（W4 T3-2）

> 用途：11/30 封版前逐项打勾，证据位与口径对齐 `docs/冲刺计划-1130.md` §10.6。
> 状态约定：✅ 已闭环　🟡 代码在仓、待云端/人工回填证据　❌ 缺口待补　➖ 非本仓范围
> 封版时本表所有数字必须能被旁边命令复现；写不出复现命令的数字不进对外材料。

## 0 封版命令序列（干净环境跑一遍，留日志）

```bash
# 0) 干净 clone + 新 venv，装依赖（运行依赖 + 开发依赖；selfcheck/pytest/ruff 在后者）
python -m pip install -r requirements.txt -r requirements-dev.txt

# 1) 建库 + 灌样本
python mcp-server/seed.py --reset
python tools/ingest_all.py

# 2) 一键自检（骨架/测试/评测/骨架/契约五步）
python tools/selfcheck.py

# 3) 回归测试
python -m pytest tests -o addopts="" -q

# 4) 终版闸门（R1–R5 结构 + 指标）
python tools/acceptance.py --stage final --with-eval

# 5) 两套同口径评测（v1 30 条 / v0 20 条），报告落 eval/reports/
python eval/run_eval.py --dataset eval/dataset/v1.jsonl --out eval/reports/final-v1
python eval/run_eval.py --dataset eval/dataset/v0.jsonl --out eval/reports/final-v0

# 6) 红线扫描：无密钥、无真实患者数据。
#    说明：下面的正则会命中命令自身里的 secret/password 字样，以及字段名等正常候选；
#    不能以「输出为空」为通过标准。逐条复核每个候选：允许保留的写明依据（字段名/示例串/文档命令），
#    确认没有未处理的真实密钥、患者数据或手机号泄露后才算通过；不要删扫描，也不要忽略全部命中。
git grep -nE "api[_-]?key|secret|password|1[3-9][0-9]{9}" -- .
```

## 1 R1–R5 逐项核对

| 项 | 判定口径（§10.6） | 复现命令 / 证据位 | 当前状态 | 责任人 |
| --- | --- | --- | --- | --- |
| R1 多模态资产 | 卡 ≥61；三类样本各 ≥20；卡字段无缺（asset_id/title/modality/anchors/entities） | `acceptance.py` A-05/A-06；`web/ledger.html`；`data/asset-cards/` | 🟡 入库 70 行；封版前在干净库复跑回填卡数/锚点数 | T3 |
| R2 本体与对齐 | 三元组 ≥50；锚点覆盖 100%；ICD-10 对齐率 ≥90%；版本号单调；每次 commit 有 changelog | `acceptance.py` A-07/A-08/A-09；`kg_query` 抽检；`version` 表 | ❌ main 37 条 / #31 分支 44 条，未达 50；A-07 口径待 T1 拍（降 40 同步 R-05 或继续补数据） | T2 / T1 |
| R3 MCP + Skills | 10 工具 + 3 Skill 包；契约校验过；Nexent 内可调用 | A-11/A-12；`tools/validate_trace.py`；M-2 远程可达、M-3 控制台 10 工具 | 🟡 10 工具/3 Skill 在仓、CI 契约校验绿；Nexent 实连截图待 T1 云端回传 | T1 / T3 |
| R4 多跳与溯源 | 三跳可跑；溯源完整率 ≥0.85；trace_id 可回放；skill_export 出模板 | `eval/reports/*.md`；`web/trace.html` 回放；`skill_export` 导出件 | 🟡 B-06 溯源 1.000；三跳跨文档 0%（路径同文档）；模板导出件待 T1-2 产物落仓 | T1 / T2 |
| R5 Nexent 可运行 | 现场提问 → 科室 → 检查 → 证据链，连跑 3 次不炸 | 录屏 + 会话 json（`agent/sessions/`） | ❌ 待 T1 在 Nexent 实跑 3 遍并回传会话记录；本机无 daemon 无法代跑 | T1 |

## 2 材料项（§10.6「材料」行）

| 材料 | 口径 | 证据 | 当前状态 | 责任人 |
| --- | --- | --- | --- | --- |
| PPT | 10 页，`materials/ppt.pdf` | T1-1 产出 | ❌ 未开始（11/23–11/26） | T1 |
| 演示视频 | 3–5 分钟，mp4 + 字幕，一次成 | `materials/`（不入仓） | ❌ 依赖 T1-1 脚本；分镜框架见 `w4-video-storyboard.md` | T3 |
| README 90 秒可跑 | §4 命令序列在干净环境按序跑通 | 干净环境录屏/日志 | 🟡 README 状态表数字过期，封版前按 `w4-doc-finalization-notes.md` 回填 | T3 |
| tag `v1.0` | 封版 main commit 打 Annotated tag | `git ls-remote --tags origin` 见 v1.0 | ❌ 未打；封版后由 T1 执行 push tag，T3 核对远端可见 | T1 / T3 |

## 3 红线（任一不过即不封版）

- [ ] 仓库内无密钥、无真实患者数据、无真实手机号/身份证/医疗单据原图（第 0 节第 6 条扫描结果逐条复核：字段名/示例串/文档命令等允许项写明依据，未处理的真实泄露清零；不以扫描输出为空作为通过标准）。
- [ ] README / 交接单 / 方案里的每个数字都有复现命令；空分母、只报最好一题的指标不写。
- [ ] 新增文档已进 `docs/README.md` 文档地图（§10.7 反例：文档没进地图不算完成）。
- [ ] `tools/acceptance.py --stage final --with-eval` 除 MANUAL 项外无 FAIL；已知缺口（A-07、B-05/B-08）在交接单如实写明，未靠改阈值/挑金标准凑绿。
- [ ] `materials/` 不入仓（§10.6）；mp4/ppt 只留本地与交付盘，不进 git。

## 4 封版后 tag 流程（备忘）

```bash
# 1) 确认 main 已是封版 commit、CI 全绿、核对表全勾
git log --oneline -1
# 2) 打 Annotated tag（T1 执行，T3 核对）
git tag -a v1.0 -m "MedPal-Cog v1.0：10 工具 / 3 Skill / 30 条评测 / 本体 v1.0"
git push origin v1.0
# 3) 远端核对
git ls-remote --tags origin
```

> tag 不指向未合并的 PR 分支；先合 main、再打 tag。周轻量 tag `w1…w3` 由 T1 在每周闸门后补打，不阻塞 v1.0。
