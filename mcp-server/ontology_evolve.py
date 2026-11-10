"""W2 进化：第二批样例文档入库 → onto_propose 抽候选 → onto_commit 发布 v1.0。

为什么单独一个模块而不是塞进 ontology_grow：
- 结构关系（科室 / 检查 / ICD 对齐）是 grow 那套「只认文档写明的写法」；
- 而「本体会长」要给评委看的是工具链动起来：先 propose 出待审 diff，再 commit 出版本，
  最后 diff_versions(v0.9, v1.0) 能回放这批新增。所以本模块把两步串起来，
  并把版本号显式钉成 v1.0 —— onto_commit 的默认 _bump 只会把 v0.9 推成 v0.10。

别名也在这里补：v0.9 的别名表只认 k27 那一片，第二批文档里的「缺铁性贫血」「血清铁蛋白」
在 v0.9 里既不进别名表、也没有三元组，问它就是拒答；v1.0 才既认得出、又答得上。
这正是「决策会变」的可观测证据，所以别名跟着版本一起来，不在 seed 里预埋。

用法：
    python mcp-server/ontology_evolve.py                                  # 交付库
    MEDPAL_DB=tmp/probe.db python mcp-server/ontology_evolve.py           # 副本
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ontology_grow  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402

BASE_VERSION = "v0.9"
NEW_VERSION = "v1.0"
NOTE = "W2 进化预演：新增 4 份样例文档（缺铁性贫血 / 甲亢 / 急性阑尾炎 / 慢阻肺）"

# 第二批实体（surface, code, scheme, entity_type, confidence）
NEW_ALIASES = [
    # 第二批样例文档（pathway_21..24）用到的实体：别名表是本体的一部分，
    # onto_propose 只能召回到别名表里已有的实体，缺一条就整条候选被判 entity_unresolved。
    ("缺铁性贫血", "D50.9", "ICD-10", "Disease", 0.95),
    ("血清铁蛋白", "EX-FERRITIN", "local", "Exam", 0.85),
    ("骨髓涂片", "EX-BM-SMEAR", "local", "Exam", 0.85),
    ("血常规", "EX-CBC", "local", "Exam", 0.92),
    ("血液内科", "DEP-HEMA", "local", "Department", 0.95),
    ("甲状腺功能亢进症", "E05.9", "ICD-10", "Disease", 0.95),
    ("甲状腺功能亢进", "E05.9", "ICD-10", "Disease", 0.9),
    ("甲状腺功能", "EX-TFT", "local", "Exam", 0.88),
    ("甲状腺超声", "EX-US-THY", "local", "Exam", 0.85),
    ("甲状腺", "EX-TFT", "local", "Exam", 0.8),
    ("急性阑尾炎", "K35.8", "ICD-10", "Disease", 0.95),
    ("腹部超声", "EX-US-ABD", "local", "Exam", 0.85),
    ("普外科", "DEP-SURG", "local", "Department", 0.95),
    ("慢性阻塞性肺疾病", "J44.9", "ICD-10", "Disease", 0.95),
    ("肺功能", "EX-PFT", "local", "Exam", 0.88),
    ("呼吸内科", "DEP-RESP", "local", "Department", 0.95),
    # may_cause 关系的尾实体：跨文档关联（溃疡→贫血、甲亢→房颤、阑尾炎→腹膜炎、慢阻肺→肺心病）
    ("心房颤动", "I48", "ICD-10", "Disease", 0.92),
    ("腹膜炎", "K65.0", "ICD-10", "Disease", 0.9),
    ("肺心病", "I27.9", "ICD-10", "Disease", 0.88),
]


def add_aliases(conn) -> int:
    """把第二批别名写进别名表；已存在就覆盖（幂等）。"""
    for surface, code, scheme, etype, conf in NEW_ALIASES:
        conn.execute(
            "INSERT OR REPLACE INTO alias (surface,code,scheme,entity_type,confidence) "
            "VALUES (?,?,?,?,?)",
            (surface, code, scheme, etype, conf),
        )
    conn.commit()
    return len(NEW_ALIASES)


def evolve(conn, version: str = NEW_VERSION) -> dict:
    """把第二批文档长进本体并发布新版本，返回可写进周报的一组计数。"""
    base = ontology_grow.grow(conn)  # 幂等：v0.9 基线（4 份文档 37 条）
    aliased = add_aliases(conn)
    # 第二批文档入库：锚点必须先落库，onto_propose 才有东西可读
    asset_ids = []
    for rel in ontology_grow.BATCH2:
        path = ROOT / rel
        hit = ontology_grow._existing(conn, path)
        aid, _ = hit if hit else ontology_grow._register(conn, path)
        asset_ids.append(aid)

    # 结构关系先挂到 v1.0（科室 / 检查 / ICD 对齐），再做工具链那一遍
    grown = ontology_grow.grow(conn, docs=ontology_grow.BATCH2, version=version)
    prop = server.onto_propose(asset_ids, scope="w2-evolve")
    if not prop.get("ok"):
        raise SystemExit("onto_propose 失败：" + str(prop.get("reason")))
    com = server.onto_commit(prop["diff_id"], version=version, note=NOTE)
    if not com.get("ok"):
        raise SystemExit("onto_commit 失败：" + str(com.get("reason")))
    diff = store.diff_versions(conn, BASE_VERSION, version)
    return {
        "base_version": BASE_VERSION,
        "new_version": version,
        "base_docs": base["docs"],
        "new_docs": grown["docs"],
        "aliases_added": aliased,
        "structural_triples": grown["triples"],
        "proposed": prop["counts"]["candidates"],
        "proposal_rejected": prop["counts"]["rejected"],
        "committed": com["added"],
        "triples_total": com["snapshot"]["triple_count"],
        "manifest_hash": com["snapshot"]["manifest_hash"],
        "diff": diff["counts"],
        "diff_id": prop["diff_id"],
    }


def main() -> int:
    db = os.environ.get("MEDPAL_DB") or str(store.DB_PATH)
    os.environ["MEDPAL_DB"] = db  # server._conn() 认这个变量
    conn = store.connect(db)
    try:
        stats = evolve(conn)
    finally:
        conn.close()
    print("本体版本:", stats["base_version"], "→", stats["new_version"])
    print("  文档  :", stats["base_docs"], "→", stats["base_docs"] + stats["new_docs"], "份")
    print("  别名 +", stats["aliases_added"], "| 结构三元组", stats["structural_triples"],
          "| 工具链候选", stats["proposed"], "（被规则挡下", stats["proposal_rejected"], "条）")
    print("  提交新增:", stats["committed"], "| 版本内总条数:", stats["triples_total"],
          "| manifest:", stats["manifest_hash"])
    print("  差分  :", stats["diff"], "| diff_id:", stats["diff_id"])
    print("  库文件:", db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
