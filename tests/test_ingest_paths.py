"""资产卡的 `source.path` 必须是仓库相对路径，换台机器也能溯源。

评审 #31 第 4 条：ingest 之后 70 张卡的 `source.path` 还是 `E:\\deepseek-data\\...`，
别人 clone 下来锚点全断。写入口在 `server.ingest_asset`，这里按真实入口回归：
- 仓库内的文件 → `data/samples/...`（POSIX 分隔符，不带盘符）
- 仓库外的文件（运行期上传）→ 保留绝对路径
- 相对入参能按仓库根解析，不依赖进程当前目录
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import server  # noqa: E402
import store  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setenv("MEDPAL_DB", str(db))
    store.connect().close()
    return db


def test_repo_sample_path_is_relative(fresh_db):
    """仓库内的样本必须写成仓库相对路径。"""
    sample = ROOT / "data" / "samples" / "pathway_k27.md"
    res = server.ingest_asset(str(sample), source_type="synthetic")
    assert res["ok"], res

    card = server.get_asset_card(asset_id=res["asset_id"])["cards"][0]
    path = card["source"]["path"]
    assert path == "data/samples/pathway_k27.md", path
    assert ":" not in path and "\\" not in path, path


def test_relative_input_resolves_against_repo_root(fresh_db):
    """传 `data/samples/...` 这种相对入参时，按仓库根找文件而不是当前目录。"""
    res = server.ingest_asset("data/samples/pathway_k27.md", source_type="synthetic")
    assert res["ok"], res
    card = server.get_asset_card(asset_id=res["asset_id"])["cards"][0]
    assert card["source"]["path"] == "data/samples/pathway_k27.md"


def test_file_outside_repo_keeps_absolute_path(fresh_db, tmp_path):
    """仓库外的文件没有相对根，保留绝对路径，不能硬编成假的相对路径。"""
    outside = tmp_path / "uploaded.md"
    outside.write_text("# 运行期上传\n\n患者需要做胃镜检查。\n", encoding="utf-8")
    res = server.ingest_asset(str(outside), source_type="synthetic")
    assert res["ok"], res

    card = server.get_asset_card(asset_id=res["asset_id"])["cards"][0]
    path = card["source"]["path"]
    assert Path(path).is_absolute(), path
    assert Path(path) == outside.resolve(), path


def test_stable_asset_id_reads_relative_source_from_repo_root(fresh_db, monkeypatch):
    """资产号按内容哈希：`source.path` 是相对路径时也必须读得到文件。

    防的错：`stable_asset_id` 用 `Path(src).is_file()` 直接判断，进程不在仓库根时
    （容器里的 /app 恰好是根，但单测/工具可能不是）会退化成「标题|路径」哈希，
    同一份文件在不同工作目录下拿到不同资产号，台账失稳。
    """
    sample = ROOT / "data" / "samples" / "pathway_k27.md"
    card = {"source": {"path": "data/samples/pathway_k27.md"}, "title": "测试"}
    monkeypatch.chdir(ROOT / "mcp-server")  # 当前目录不是仓库根
    aid = store.stable_asset_id(card)
    raw = sample.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha1(raw).hexdigest()[:6]
    expect = "AST-" + datetime.now(store.CST).strftime("%Y") + "-" + digest
    assert aid == expect, (aid, expect)