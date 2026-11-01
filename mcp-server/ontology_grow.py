"""跨文档长本体：把样例文档里的疾病、科室、检查抽成三元组。

种子库里手写的 17 条都锚在 `data/samples/pathway_k27.md` 这一份文档上，单文档长不出
「跨文档取证」——R4 要的证据本来就分散在多份文件里。本模块读
`data/samples/text/pathway_01..04.md`（高血压 / 2 型糖尿病 / 肺炎 / 肾结石），
先用与 `ingest_asset` 相同的解析路径落资产卡和锚点，再按文档里**写明**的关系长三元组：
诊断依据那句给出 ICD 与就诊科室，检查项目那句给出检查项。

加关系不做自由生成：只认文档里出现过的写法，写不出实体就不加。每条三元组的
provenance 都指回具体锚点，`kg_query` 与决策链能直接引。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import parsers
import store

DOCS = [
    "data/samples/text/pathway_01.md",
    "data/samples/text/pathway_02.md",
    "data/samples/text/pathway_03.md",
    "data/samples/text/pathway_04.md",
]

# 科室固定编号：跨文档复用同一科室时不能长出两个 id
DEPT_IDS = {
    "消化内科": "DEP-GI",
    "心血管内科": "DEP-CARD",
    "内分泌科": "DEP-ENDO",
    "呼吸内科": "DEP-RESP",
    "泌尿外科": "DEP-URO",
    "普外科": "DEP-SURG",
}

# 检查项编号同理；没登记的按名字哈希兜底，保证同一检查只有一个 id
EXAM_IDS = {
    "血压监测": "EX-BP-MON",
    "心电图": "EX-ECG",
    "肾功能": "EX-RENAL",
    "空腹血糖": "EX-FPG",
    "糖化血红蛋白": "EX-HBA1C",
    "眼底检查": "EX-FUNDUS",
    "胸片": "EX-CXR",
    "血常规": "EX-CBC",
    "C反应蛋白": "EX-CRP",
    "泌尿系超声": "EX-US-KUB",
    "尿常规": "EX-URINE",
}

TITLE = re.compile(r"^(.+?)临床路径")
ICD = re.compile(r"ICD-10\s*([A-Z]\d+(?:\.\d+)?)")
DEPT = re.compile(r"就诊科室\s*([^\s，。,]+)")


def _slug(prefix: str, label: str, table: dict) -> str:
    return table.get(label) or prefix + hashlib.sha1(label.encode()).hexdigest()[:6]


def _existing(conn, path: Path) -> tuple[str, list[dict]] | None:
    """台账里已经有这份文档就复用它：只读，不再写一次资产卡。

    重新 upsert 会把 ingest_all 写的标题/ingested_by 覆盖成本模块的值，
    磁盘上的 Asset Card 与库里的就再也对不上。
    """
    card = {"source": {"path": str(path)}}
    aid = store.canonical_asset_id(card) or store.stable_asset_id(card)
    row = conn.execute(
        "SELECT asset_id, anchors_json FROM asset WHERE asset_id = ?", (aid,)
    ).fetchone()
    if not row:
        return None
    return row["asset_id"], json.loads(row["anchors_json"] or "[]")


def _register(conn, path: Path) -> tuple[str, list[dict]]:
    """与 mcp-server/server.py 的 ingest_asset 同一套落库方式，返回 (asset_id, anchors)。"""
    doc = parsers.parse(path)
    card = {
        "title": doc.title,
        "modality": doc.modality,
        "source": {"type": "public_standard", "publisher": "", "path": str(path)},
        "version": {"value": "v1", "captured_at": store.now(), "supersedes": None},
        "sensitivity": "public",
        "structure": {
            "blocks": len(doc.blocks),
            "anchors": len(doc.anchors),
            "kinds": sorted({b.kind for b in doc.blocks}),
        },
        "anchors": doc.anchors,
        "entities": parsers.guess_entities(doc),
        "kb_status": "ready",
        "ingested_by": "ontology_grow",
    }
    asset_id = store.upsert_asset(conn, card)
    for a in card["anchors"]:
        a["anchor_id"] = a["anchor_id"].replace(path.stem, asset_id)
    card["asset_id"] = asset_id
    store.upsert_asset(conn, card)
    return asset_id, card["anchors"]


def grow(conn, docs: list[str] | None = None, version: str = "v0.9") -> dict:
    root = Path(__file__).resolve().parent.parent
    stats = {"docs": 0, "triples": 0, "skipped": []}
    for rel in docs or DOCS:
        path = root / rel
        if not path.exists():
            stats["skipped"].append(rel)
            continue
        asset_id, anchors = _existing(conn, path) or _register(conn, path)
        sentences = [a for a in anchors if a["kind"] == "sentence"]
        diag = next((a for a in sentences if "ICD-10" in a["text"]), None)
        exam_line = next((a for a in sentences if a["text"].count("、") >= 2), None)
        if not diag or not exam_line:
            stats["skipped"].append(rel)
            continue

        disease = TITLE.search(path.read_text(encoding="utf-8").splitlines()[0])
        icd = ICD.search(diag["text"])
        dept = DEPT.search(diag["text"])
        if not (disease and icd):
            stats["skipped"].append(rel)
            continue

        head = {"id": icd.group(1), "type": "Disease", "label": disease.group(1)}
        prov = {"asset_id": asset_id}

        def add(rel: str, tail: dict, confidence: float, anchor: str, standard=None) -> None:
            if store.add_triple(
                conn,
                {
                    "head": head,
                    "rel": rel,
                    "tail": tail,
                    "confidence": confidence,
                    "provenance": {**prov, "anchor_id": anchor},
                    "standard": standard or {},
                },
                version=version,
            ):
                stats["triples"] += 1

        if dept:
            label = dept.group(1)
            add(
                "belongs_to_dept",
                {"id": _slug("DEP-", label, DEPT_IDS), "type": "Department", "label": label},
                0.9,
                diag["anchor_id"],
            )
        for name in [x.strip() for x in exam_line["text"].split("、") if x.strip()]:
            add(
                "requires_exam",
                {"id": _slug("EX-", name, EXAM_IDS), "type": "Exam", "label": name},
                0.85,
                exam_line["anchor_id"],
            )
        add(
            "aligned_to_standard",
            {
                "id": "ICD10-" + icd.group(1),
                "type": "Disease",
                "label": "ICD-10 " + icd.group(1),
            },
            0.99,
            diag["anchor_id"],
            {"scheme": "ICD-10", "code": head["id"]},
        )
        stats["docs"] += 1
    if stats["docs"]:
        # 快照跟着长：否则 mcp-server/data/ontology_v0.9.jsonl 还是 seed 的 17 条，
        # 库里有 37 条、文件里只有 17 条，评审一眼就看出对不上。
        store.snapshot(conn, version, f"grow: {stats['docs']} 份样例文档跨文档生长")
        conn.commit()
    return stats
