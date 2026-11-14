"""生成资产台账静态页 web/ledger.html。

读 data/asset-cards/*.json，输出单文件 HTML：无后端、无外链、双击可开。
表格行在生成时预渲染，关掉 JS 也能完整看；内联 JS 只做搜索与模态筛选。

用法：
    python tools/gen_ledger.py           # 生成 web/ledger.html
    python tools/gen_ledger.py --check   # 只校验：内容是否最新、有没有绝对路径泄漏

生成结果不含时间戳，同输入重复跑逐字节一致，git diff 稳定。
页面自带基线清单（`<meta name="ledger-baseline">`）：执行过 `ingest_all` 之后
工作区的卡会被重写、卡 id 会变，此时判等没有意义，`--check` 与测试只做结构校验。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
CARDS_DIR = ROOT / "data" / "asset-cards"
OUT_PATH = ROOT / "web" / "ledger.html"

CORE_MODALITIES = (("text", "文本"), ("table", "表格"), ("image_report", "图文"))
EXTRA_LABEL = {"pdf_text": "PDF文本"}  # W1 接入 ingest_asset 后新增的模态
MODALITY_LABEL = {**dict(CORE_MODALITIES), **EXTRA_LABEL}
MIN_CARDS = 61  # §10.2 A-05 的条数下限；台账页不许少于它

# 生成产物里出现盘符路径 = 把某台机器的工作目录写进了仓库，直接判失败
ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]")

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>资产台账 · medpal-cog</title>
<meta name="ledger-baseline" content="<!--BASELINE-->">
<style>
* { box-sizing: border-box; margin: 0; padding: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
body { background: #f4f7fa; padding: 24px; color: #222; }
.container { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 24px; font-weight: 600; margin-bottom: 6px; }
.sub { font-size: 13.5px; color: #666; margin-bottom: 18px; }
.chips { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }
.chip { background: #fff; border-radius: 8px; padding: 12px 16px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.chip .k { font-size: 12.5px; color: #888; }
.chip .v { font-size: 22px; font-weight: 600; margin-top: 2px; }
.chip .v.red { color: #cf1322; }
.bar { background: #fff; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px;
       box-shadow: 0 1px 4px rgba(0,0,0,0.08); display: flex; flex-wrap: wrap;
       gap: 8px; align-items: center; font-size: 14px; }
.bar input[type=text] { flex: 1 1 240px; min-width: 200px; padding: 7px 10px;
       border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; }
.btn { border: 1px solid #d9d9d9; background: #fff; border-radius: 6px;
       padding: 6px 12px; font-size: 13.5px; cursor: pointer; color: #444; }
.btn.on { background: #1677ff; border-color: #1677ff; color: #fff; }
.bar label { display: flex; align-items: center; gap: 5px; color: #555; }
.bar .shown { margin-left: auto; color: #888; font-size: 13px; }
.warn-box { background: #fff2f2; border: 1px solid #ffccc7; border-radius: 8px;
            padding: 14px 18px; margin-bottom: 16px; }
.warn-box h2 { font-size: 16px; color: #cf1322; margin-bottom: 8px; }
.warn-box li { font-size: 13.5px; color: #a8071a; margin: 4px 0 4px 18px; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
        overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); font-size: 13.5px; }
thead th { background: #fafbfd; text-align: left; padding: 11px 12px; font-weight: 600;
           color: #333; border-bottom: 1px solid #e8ecf2; white-space: nowrap; }
tbody td { padding: 10px 12px; border-bottom: 1px solid #f0f2f5; vertical-align: top; }
tbody tr.bad { background: #fffafa; }
.mono { font-family: Consolas, monospace; font-size: 12.5px; }
.muted { color: #888; font-size: 12.5px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
         font-size: 12px; white-space: nowrap; }
.badge.text { background: #e8f3ff; color: #0958d9; }
.badge.table { background: #eaf7ee; color: #237804; }
.badge.image_report { background: #f9f0ff; color: #722ed1; }
.badge.pdf_text { background: #fff7e6; color: #ad6800; }
.badge.other { background: #f2f2f2; color: #595959; }
.num0 { color: #cf1322; font-weight: 600; }
.foot { margin-top: 18px; font-size: 12.5px; color: #888; line-height: 1.7; }
.foot code { font-family: Consolas, monospace; background: #eef1f5; padding: 1px 5px;
             border-radius: 4px; }
</style>
</head>
<body>
<div class="container">
<h1>资产台账 · medpal-cog</h1>
<p class="sub"><!--META--></p>
<div class="chips">
<!--SUMMARY-->
</div>
<!--WARN-->
<div class="bar">
  <input type="text" id="q" placeholder="搜资产号 / 标题 / 实体" autocomplete="off">
  <button class="btn on" data-mod="all">全部</button>
<!--FILTERS-->
  <label><input type="checkbox" id="warnOnly">只看告警</label>
  <span class="shown" id="shown"></span>
</div>
<table id="ledger">
  <thead>
    <tr>
      <th>资产号</th><th>标题</th><th>模态</th><th>来源</th>
      <th>锚点</th><th>实体</th><th>知识库</th>
    </tr>
  </thead>
  <tbody>
<!--ROWS-->
  </tbody>
</table>
<div class="foot">
  数据来源 <code>data/asset-cards/*.json</code>，本页由
  <code>python tools/gen_ledger.py</code> 生成，不要手改。
  校验 <code>python tools/gen_ledger.py --check</code>。
  同一份输入重复生成逐字节一致；卡里若写着本机绝对路径，生成器会中断并报出是哪张卡。
</div>
</div>
<script>
var rows = Array.prototype.slice.call(document.querySelectorAll('#ledger tbody tr'));
var mod = 'all';
var btnList = Array.prototype.slice.call(document.querySelectorAll('.btn'));
function apply() {
  var q = document.getElementById('q').value.trim().toLowerCase();
  var warnOnly = document.getElementById('warnOnly').checked;
  var shown = 0;
  rows.forEach(function (r) {
    var okMod = (mod === 'all') || (r.getAttribute('data-mod') === mod);
    var okQ = !q || r.getAttribute('data-text').indexOf(q) !== -1;
    var okWarn = !warnOnly || r.getAttribute('data-warn') === '1';
    var show = okMod && okQ && okWarn;
    r.style.display = show ? '' : 'none';
    if (show) { shown += 1; }
  });
  document.getElementById('shown').textContent = '显示 ' + shown + ' / ' + rows.length;
}
btnList.forEach(function (b) {
  b.addEventListener('click', function () {
    mod = b.getAttribute('data-mod');
    btnList.forEach(function (x) { x.classList.remove('on'); });
    b.classList.add('on');
    apply();
  });
});
document.getElementById('q').addEventListener('input', apply);
document.getElementById('warnOnly').addEventListener('change', apply);
apply();
</script>
</body>
</html>
"""


def is_absolute_path(raw: str) -> bool:
    """判断卡里的 source.path 是不是本机绝对路径（兼容 Windows / POSIX 写法）。"""
    text = raw.strip().replace("\\", "/")
    return Path(text).is_absolute() or PureWindowsPath(text).is_absolute()


def repo_relative(raw: str) -> str:
    """把 source.path 归一成仓库相对路径；认不出 data/ 就退回文件名。

    只认 `data/` 开头或 `/data/` 这一段的写法——`E:\\deepseek-data\\...`
    里那个 `data` 是目录名的一部分，不能当仓库根。
    """
    text = raw.strip().replace("\\", "/")
    if text.startswith("data/"):
        return text
    index = text.find("/data/")
    if index != -1:
        return text[index + 1:]
    return Path(text).name or "（未登记）"


def load_cards() -> list[dict]:
    files = sorted(CARDS_DIR.glob("*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


# 页面里写死的基线清单：生成这张页时用的是哪些卡。
# 有了它，判等就不必依赖 git（也不怕工作区被 ingest 写过而多出卡）。
BASELINE_RE = re.compile(r'<meta name="ledger-baseline" content="([^"]*)">')


def page_baseline(doc: str) -> list[str]:
    """从页面里取回基线卡 id 清单。"""
    match = BASELINE_RE.search(doc)
    if not match:
        return []
    return [item for item in match.group(1).split(",") if item]


def check_page(cards: list[dict], doc: str) -> list[str]:
    """页面 vs 当前卡目录：没漂移就要求逐字节一致，漂移了只做结构校验。

    为什么要分两种状态：`acceptance.py --stage w2` 会先跑 `seed --reset` +
    `ingest_all`，把 `data/samples` 里尚未登记进仓库的样本写成卡（62 → 69）。
    ——而且它连卡 id 都会重新生成（实测有一张基线卡 `AST-2026-c87d1e` 在
    ingest 后就不存在了），所以工作区里的卡集合既不是基线的超集、也无法逐张对上。
    这时「页面是否最新」在工作区里根本没有判据，只能校验页面自身结构：
    基线清单在、每张基线卡都渲染进页面、行数对得上、没有盘符路径。

    「页面与卡不同步」这件事仍然有闸门：正常开发态（改卡、id 不变）两个集合相等，
    走逐字节判等；干净 clone 上 `python tools/gen_ledger.py --check` 也是这条。
    """
    problems = []
    baseline = page_baseline(doc)
    if not baseline:
        problems.append("台账页里没有基线清单（<meta name=ledger-baseline>），重跑生成器")
        return problems

    current = {str(card.get("asset_id", "")) for card in cards}
    if current == set(baseline):
        if doc != build_page(cards):
            problems.append("web/ledger.html 与当前资产卡不一致，重跑 python tools/gen_ledger.py")
        return problems

    not_rendered = [item for item in baseline if item not in doc]
    if not_rendered:
        problems.append(f"{len(not_rendered)} 张基线卡没有渲染进页面：{not_rendered[:3]}")
    rows = doc.count("<tr data-mod=")
    if rows != len(baseline):
        problems.append(f"台账页行数 {rows} 与基线卡数 {len(baseline)} 不一致")
    if ABS_PATH_RE.search(doc):
        problems.append("台账页里出现了盘符路径")
    return problems


def structure_of(card: dict) -> dict:
    return card.get("structure") or {}


def anchors_of(card: dict) -> int:
    return int(structure_of(card).get("anchors") or 0)


def summarize(cards: list[dict]) -> dict:
    modality = Counter(card.get("modality", "") for card in cards)
    kb_status = Counter((card.get("kb") or {}).get("status", "") for card in cards)
    summary = {
        "total": len(cards),
        "modality": modality,
        "anchors": sum(anchors_of(card) for card in cards),
        "kb_status": kb_status,
        "abs_path": [card for card in cards
                     if is_absolute_path((card.get("source") or {}).get("path", ""))],
        "zero_anchor": [card for card in cards if anchors_of(card) == 0],
        "no_entity": [card for card in cards if not card.get("entities")],
        "missing_modality": [
            label for key, label in CORE_MODALITIES if modality.get(key, 0) == 0
        ],
    }
    return summary


def render_row(card: dict) -> str:
    asset_id = card.get("asset_id", "")
    title = card.get("title", "")
    modality = card.get("modality", "")
    label = MODALITY_LABEL.get(modality, modality or "未标")
    source = card.get("source") or {}
    src_line = html.escape(str(source.get("type", ""))) or "—"
    path_line = html.escape(repo_relative(str(source.get("path", ""))))
    anchors = anchors_of(card)
    entities = card.get("entities") or []
    kb = (card.get("kb") or {}).get("status", "") or "—"
    warn = anchors == 0 or not entities
    anchors_cls = "num0" if anchors == 0 else "mono"
    entities_text = html.escape("、".join(str(x) for x in entities)) if entities else "（无）"
    badge_cls = modality if modality in MODALITY_LABEL else "other"
    search_text = " ".join([asset_id, title, modality, path_line, " ".join(
        str(x) for x in entities)]).lower()
    return (
        f'    <tr data-mod="{html.escape(modality)}" data-warn="{1 if warn else 0}" '
        f'data-text="{html.escape(search_text)}">'
        f'<td class="mono">{html.escape(asset_id)}</td>'
        f"<td>{html.escape(title)}</td>"
        f'<td><span class="badge {badge_cls}">{html.escape(label)}</span></td>'
        f'<td><span class="mono">{src_line}</span><br>'
        f'<span class="muted mono">{path_line}</span></td>'
        f'<td class="{anchors_cls}">{anchors}</td>'
        f"<td>{entities_text}</td>"
        f'<td><span class="mono">{html.escape(str(kb))}</span></td>'
        "</tr>"
    )


def render_summary(summary: dict) -> str:
    modality = summary["modality"]
    parts = [
        ("资产卡", str(summary["total"]), ""),
        ("锚点合计", str(summary["anchors"]), ""),
    ]
    for key, label in CORE_MODALITIES:
        parts.append((label, str(modality.get(key, 0)), ""))
    for key, label in EXTRA_LABEL.items():
        if modality.get(key, 0):
            parts.append((label, str(modality.get(key, 0)), ""))
    parts.append(("知识库 ready", str(summary["kb_status"].get("ready", 0)), ""))
    warn_count = (len(summary["zero_anchor"]) + len(summary["no_entity"])
                  + len(summary["missing_modality"]))
    parts.append(("告警", str(warn_count), "red" if warn_count else ""))
    chips = []
    for key, value, cls in parts:
        value_cls = f"v {cls}" if cls else "v"
        chips.append(f'  <div class="chip"><div class="k">{key}</div>'
                     f'<div class="{value_cls}">{value}</div></div>')
    return "\n".join(chips)


def render_filters(cards: list[dict]) -> str:
    """核心三类固定给按钮；pdf_text 之类新模态只在真的有卡时才出现。"""
    keys = [key for key, _ in CORE_MODALITIES]
    keys += [key for key in EXTRA_LABEL if any(c.get("modality") == key for c in cards)]
    buttons = [f'  <button class="btn" data-mod="{key}">'
               f"{MODALITY_LABEL.get(key, key)}</button>" for key in keys]
    return "\n".join(buttons)


def brief_ids(cards: list[dict], limit: int = 6) -> str:
    ids = [card.get("asset_id", "") for card in cards]
    if len(ids) <= limit:
        return "、".join(ids)
    head = "、".join(ids[:limit])
    return f"{head}…… 共 {len(ids)} 张（下表红色行可逐条看）"


def render_meta(summary: dict) -> str:
    modality = summary["modality"]
    groups = "、".join(f"{label} {modality.get(key, 0)}" for key, label in CORE_MODALITIES)
    extra = [f"{label} {modality[key]}"
             for key, label in EXTRA_LABEL.items() if modality.get(key, 0)]
    if extra:
        groups = f"{groups}、{'、'.join(extra)}"
    return (f"共 {summary['total']} 份（{groups}）；锚点合计 {summary['anchors']} 个。"
            "本页只读资产卡，不含解析与检索逻辑。")


def render_warn(summary: dict) -> str:
    items = []
    if summary["missing_modality"]:
        missing = "、".join(summary["missing_modality"])
        items.append(f"本批缺 {missing} 模态，R1 的多模态覆盖不足。")
    if summary["zero_anchor"]:
        items.append(f"锚点数为 0（按 S1 口径视为入库失败）：{brief_ids(summary['zero_anchor'])}")
    if summary["no_entity"]:
        items.append(f"识别实体为空：{brief_ids(summary['no_entity'])}")
    if summary["abs_path"]:
        count = len(summary["abs_path"])
        items.append(
            f"{count} / {summary['total']} 张卡的 source.path 是本机绝对路径"
            "（页面上已归一成仓库相对路径显示）。这是数据面待修的坑："
            "别人 clone 下来锚点溯源会断链，修复点在写卡的 `mcp-server/server.py`。"
        )
    if not items:
        return ""
    body = "\n".join(f"    <li>{html.escape(item)}</li>" for item in items)
    return ('<div class="warn-box">\n  <h2>告警</h2>\n  <ul>\n'
            f"{body}\n  </ul>\n</div>")


def build_page(cards: list[dict]) -> str:
    summary = summarize(cards)
    rows = "\n".join(render_row(card) for card in cards)
    baseline = ",".join(str(card.get("asset_id", "")) for card in cards)
    doc = TEMPLATE
    doc = doc.replace("<!--BASELINE-->", html.escape(baseline))
    doc = doc.replace("<!--META-->", render_meta(summary))
    doc = doc.replace("<!--SUMMARY-->", render_summary(summary))
    doc = doc.replace("<!--WARN-->", render_warn(summary))
    doc = doc.replace("<!--FILTERS-->", render_filters(cards))
    doc = doc.replace("<!--ROWS-->", rows)
    return doc


def verify(cards: list[dict], doc: str) -> list[str]:
    """生成产物的硬性自检；返回问题清单，空表示通过。"""
    problems = []
    if len(cards) < MIN_CARDS:
        problems.append(f"资产卡只有 {len(cards)} 张，少于下限 {MIN_CARDS} 张（A-05）")
    leaked = ABS_PATH_RE.findall(doc)
    if leaked:
        problems.append(f"生成页里出现 {len(leaked)} 处盘符路径，绝对路径泄漏")
    for card in cards:
        asset_id = card.get("asset_id", "")
        if asset_id not in doc:
            problems.append(f"{asset_id} 没有出现在台账页里")
    if cards and doc.count("<tr data-mod=") != len(cards):
        problems.append("台账页行数与资产卡数量不一致")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/校验资产台账静态页 web/ledger.html")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args(argv)

    cards = load_cards()
    doc = build_page(cards)
    problems = verify(cards, doc)
    if problems:
        for item in problems:
            print(f"FAIL {item}", file=sys.stderr)
        return 1

    if args.check:
        if not OUT_PATH.exists():
            print(f"FAIL 缺 {OUT_PATH.relative_to(ROOT)}，先跑 python tools/gen_ledger.py")
            return 1
        current = OUT_PATH.read_text(encoding="utf-8")
        problems = check_page(cards, current)
        if problems:
            for item in problems:
                print(f"FAIL {item}", file=sys.stderr)
            return 1
        extra = len(cards) - len(page_baseline(current))
        note = f"，另有 {extra} 张未入库的卡未纳入页面（基线快照）" if extra else ""
        print(f"OK 基线 {len(page_baseline(current))} 张卡，"
              f"{OUT_PATH.relative_to(ROOT)} 与基线一致{note}")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(doc, encoding="utf-8", newline="\n")
    summary = summarize(cards)
    print(f"OK 已生成 {OUT_PATH.relative_to(ROOT)}：{len(cards)} 张卡，"
          f"锚点 {summary['anchors']} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
