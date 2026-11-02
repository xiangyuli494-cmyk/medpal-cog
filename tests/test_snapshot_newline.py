"""快照文件必须与平台无关：Windows 上写出来也不能带 CRLF。

原因：仓库 .gitattributes 是 * text=auto eol=lf，快照是跟踪文件。
写入端若用默认 newline，Windows 上每次 seed / ingest / 验收都会让
mcp-server/data/ontology_v0.9.jsonl 重新变脏（内容一致但工作区 CRLF），
同事一跑就看到一堆假改动。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import store  # noqa: E402


def _triple():
    return {
        "head": {"id": "K1", "type": "Disease", "label": "测试病"},
        "rel": "has_symptom",
        "tail": {"id": "SYM-1", "type": "Symptom", "label": "测试症"},
        "confidence": 0.9,
        "provenance": {"asset_id": "AST-2026-000137", "anchor_id": "AST-2026-000137#s1.p1.c1"},
    }


def test_snapshot_writes_lf_only(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    conn = store.connect(tmp_path / "t.db")
    store.add_triple(conn, _triple())
    info = store.snapshot(conn, "v0.9", note="test")
    raw = Path(info["snapshot_path"]).read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    conn.close()
