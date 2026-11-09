"""本体版本差分只读查询（T2 · issue #7）。

用法：
    python tools/onto_diff.py --list
    python tools/onto_diff.py --from v0.9 --to v1.0
    python tools/onto_diff.py --from v0.9 --to tests/fixtures/ontology_v1.0_demo.jsonl --format json

设计约束（见 issue #7）：
1. 输入版本号，不要求调用方知道快照文件叫什么；也接受直接给 .jsonl 路径。
2. 只读：只读快照，不写库、不建快照、不改 mcp-server/server.py 里 10 个工具的签名。
3. 差分口径复用 ontology/diff.py：以 triple_id 为身份，新增/删除/改置信度三态，
   外加 id_drift（编号漂移不算删一条加一条）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "mcp-server" / "data"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ontology.diff import (  # noqa: E402
    DiffVersionInvalid,
    DiffVersionNotFound,
    diff_versions,
    render_report,
)


def normalize(version: str) -> str:
    """把 0.9 / v0.9 / ontology_v0.9 / ontology_v0.9.jsonl 统一成 v0.9。"""
    v = (version or "").strip()
    if v.lower().startswith("ontology_"):
        v = v[len("ontology_"):]
    if v.lower().endswith(".jsonl"):
        v = v[: -len(".jsonl")]
    if not v.lower().startswith("v"):
        v = "v" + v
    return v


def available(data_dir: Path) -> list[str]:
    """列出目录里现有的版本号，报错时一并回显，省得调用方猜。"""
    if not data_dir.is_dir():
        return []
    return sorted(p.stem[len("ontology_"):] for p in data_dir.glob("ontology_*.jsonl"))


def resolve(spec: str, data_dir: Path) -> Path:
    """版本号先当路径试，再按 data_dir 拼 ontology_<版本>.jsonl。"""
    candidate = Path(spec)
    if candidate.suffix == ".jsonl" or candidate.is_file():
        if candidate.is_file():
            return candidate
        raise DiffVersionNotFound("快照文件不存在：" + str(candidate))
    version = normalize(spec)
    path = data_dir / ("ontology_" + version + ".jsonl")
    if not path.exists():
        names = available(data_dir)
        hint = "、".join(names) if names else "（该目录下没有 ontology_*.jsonl）"
        raise DiffVersionNotFound(
            "版本 " + version + " 没有快照；" + str(data_dir) + " 里现有：" + hint
        )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按版本号查本体差分：新增 / 删除 / 改置信度")
    parser.add_argument("--from", dest="from_version", help="旧版本号（v0.9）或快照路径")
    parser.add_argument("--to", dest="to_version", help="新版本号（v1.0）或快照路径")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="快照目录，默认 mcp-server/data（测试可用临时目录）",
    )
    parser.add_argument("--list", action="store_true", help="列出可用版本后退出")
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)

    if args.list:
        names = available(data_dir)
        print("\n".join(names) if names else "（无快照）")
        return 0
    if not args.from_version or not args.to_version:
        parser.error("--from 与 --to 必填（或用 --list 看有哪些版本）")

    try:
        old = resolve(args.from_version, data_dir)
        new = resolve(args.to_version, data_dir)
        diff = diff_versions(old, new)
    except DiffVersionNotFound as exc:
        print("差分失败：" + str(exc), file=sys.stderr)
        return 2
    except DiffVersionInvalid as exc:
        print("差分失败：快照内容不合法（" + str(exc) + "）", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print(render_report(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
