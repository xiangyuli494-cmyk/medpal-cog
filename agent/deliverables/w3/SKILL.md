---
name: t1-department-evidence-draft
description: 由 trace TR-20261117-914A 自动导出，覆盖步骤 3 步
allowed-tools: [std_align, kg_query]
tags: [auto-exported, medical]
---

## 何时用
问题形态与「上腹隐痛的科室建议有哪些可核验依据？」相近时。

## 步骤
1. std_align -> ['SYM-EPI']
2. kg_query -> ['SYM-EPI', 'K27', 'DEP-GI']
3. conclude -> {'dept': '消化内科', 'exams': []}

## 禁止
- 引用无 anchor_id 的内容
- 给出药品剂量
