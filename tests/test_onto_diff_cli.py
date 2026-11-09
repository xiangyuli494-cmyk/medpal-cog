"""tools/onto_diff.py 的只读查询测试（T2 · issue #7）。

覆盖：新增 / 删除 / 改置信度 三态、版本号归一化、版本不存在时报错并回显可用版本、--list。
全部离线：在临时目录里造两版快照，不碰真实库、不联网。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import onto_diff  # noqa: E402


def write_snapshot(path: Path, rows: list[dict]) -> Path:
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def triple(tid: str, head: str, rel: str, tail: str, conf: float = 0.9) -> dict:
    return {
        "triple_id": tid,
        "head_id": head,
        "rel": rel,
        "tail_id": tail,
        "confidence": conf,
        "asset_id": "AST-2026-000137",
        "anchor_id": "AST-2026-000137#s1.h",
    }


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    write_snapshot(
        data / "ontology_v1.0.jsonl",
        [
            triple("T-a", "K27", "belongs_to_dept", "DEP-GI"),
            triple("T-b", "K27", "requires_exam", "EX-GASTRO"),
            triple("T-c", "K29", "has_symptom", "SYM-EPI", 0.7),
        ],
    )
    write_snapshot(
        data / "ontology_v1.1.jsonl",
        [
            triple("T-a", "K27", "belongs_to_dept", "DEP-GI"),
            triple("T-b", "K27", "requires_exam", "EX-GASTRO", 0.95),
            triple("T-d", "K27", "treated_by", "DRUG-PPI", 0.88),
        ],
    )
    return data


def run(data: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = onto_diff.main(["--data-dir", str(data), *args])
    out, err = capsys.readouterr()
    return code, out, err


def test_added_and_removed(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(data_dir, capsys, "--from", "v1.0", "--to", "v1.1", "--format", "json")
    import json as _json

    diff = _json.loads(out)
    assert code == 0
    assert diff["counts"] == {"added": 1, "removed": 1, "modified": 1}
    assert [r["head"]["id"] for r in diff["added"]] == ["K27"]
    assert diff["added"][0]["rel"] == "treated_by"
    assert [r["head"]["id"] for r in diff["removed"]] == ["K29"]


def test_modified_confidence(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(data_dir, capsys, "--from", "v1.0", "--to", "v1.1", "--format", "json")
    diff = json.loads(out)
    assert code == 0
    assert len(diff["modified"]) == 1
    record = diff["modified"][0]
    assert record["triple_id"] == "T-b"
    assert record["changed_fields"] == ["confidence"]
    assert record["old"]["confidence"] == 0.9
    assert record["new"]["confidence"] == 0.95


def test_text_report_with_bare_version(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 不带 v 前缀、给 1.0 也要能解析成 v1.0
    code, out, _ = run(data_dir, capsys, "--from", "1.0", "--to", "1.1")
    assert code == 0
    assert "新增 1" in out
    assert "删除 1" in out
    assert "修改 1" in out
    assert "treated_by" in out


def test_missing_version_lists_available(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(data_dir, capsys, "--from", "v9.9", "--to", "v1.1")
    assert code == 2
    assert "v9.9" in err
    assert "v1.0" in err and "v1.1" in err


def test_list_versions(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(data_dir, capsys, "--list")
    assert code == 0
    assert out.split() == ["v1.0", "v1.1"]
