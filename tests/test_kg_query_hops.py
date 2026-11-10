"""kg_query 多跳抽检（T2 · issue #7）：以 K27 为种子，两跳能拿回科室与检查，hops 自洽。

口径来自 issue #7：max_hops=2 时应能取到科室（DEP-GI）与检查（EX-GASTRO / EX-HP-BT），
且每条 path 的 hops 字段等于节点数减一、不超过 max_hops。
库是临时库（tmp/kg_hops.db），每次跑重建，不影响交付快照。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
TMP.mkdir(exist_ok=True)
DB = TMP / "kg_hops.db"
if DB.exists():
    DB.unlink()

sys.path.insert(0, str(ROOT / "mcp-server"))
import store  # noqa: E402

store.DB_PATH = DB
store.DATA_DIR = TMP
store.REPORT_DIR = TMP / "reports"

import seed  # noqa: E402

seed.main(reset=True)


def query(max_hops: int, seeds: list[str] | None = None) -> dict:
    conn = store.connect()
    try:
        return store.kg_query(conn, seeds or ["K27"], max_hops=max_hops, limit=100)
    finally:
        conn.close()


def reached_nodes(result: dict) -> set[str]:
    out: set[str] = set()
    for path in result["paths"]:
        out.update(path["nodes"])
    return out


def test_two_hops_reach_dept_and_exam() -> None:
    result = query(2)
    assert result["ok"] is True
    assert "K27" in result["resolved"]
    assert {"DEP-GI", "EX-GASTRO", "EX-HP-BT"} <= reached_nodes(result)
    # 至少有一条真的是两跳，否则 max_hops=2 等于没生效
    assert any(p["hops"] == 2 for p in result["paths"])


def test_hops_field_is_consistent() -> None:
    result = query(2)
    for path in result["paths"]:
        assert path["hops"] == len(path["nodes"]) - 1
        assert 1 <= path["hops"] <= 2
        assert len(path["steps"]) == path["hops"]
        for step in path["steps"]:
            assert step["provenance"]["asset_id"]
            assert step["provenance"]["anchor_id"]


def test_one_hop_is_subset_of_two_hops() -> None:
    one = query(1)
    two = query(2)
    assert one["ok"] is True
    assert all(p["hops"] == 1 for p in one["paths"])
    assert reached_nodes(one) <= reached_nodes(two)
    # 胃炎只能经「上腹隐痛」两跳到达，一跳不该出现
    assert "K29" not in reached_nodes(one)
    assert "K29" in reached_nodes(two)


def test_unknown_seed_is_reported_as_unresolved() -> None:
    result = query(2, ["不存在的疾病XYZ"])
    assert result["ok"] is False
    assert result["unresolved"] == ["不存在的疾病XYZ"]
    assert result["paths"] == []
    assert result["reason"] == "no_path"
