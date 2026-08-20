"""
vault_io.py — DominionVault shared read/write module
Atomic writes, lane discipline, Obsidian-compatible Markdown + YAML frontmatter
"""
import os, json, tempfile, re
from datetime import datetime
from pathlib import Path

VAULT_ROOT = Path.home() / "dominion_vault"

LANES = {
    "inbox":   "00-inbox",
    "research":"10-research",
    "deals":   "20-deals",
    "surplus": "30-surplus-cases",
    "manual":  "40-manual",
    "meta":    "90-meta",
}

def _lane_path(lane):
    folder = LANES.get(lane, lane)
    p = VAULT_ROOT / folder
    p.mkdir(parents=True, exist_ok=True)
    return p

def _slug(title):
    return re.sub(r'[^\w\-]', '_', title.lower())[:60]

def write_note(title, body, lane="inbox", tags=None, metadata=None):
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H%M")
    filename = f"{stamp}_{_slug(title)}.md"
    target = _lane_path(lane) / filename
    fm = {"title": title, "lane": lane, "created": now.strftime("%Y-%m-%d %H:%M"), "tags": tags or []}
    if metadata:
        fm.update(metadata)
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item in v:
                fm_lines.append(f"  - {item}")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines += ["---", "", f"# {title}", "", body]
    content = "\n".join(fm_lines)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    os.replace(tmp_path, target)
    return str(target)

def read_note(filename, lane=None):
    if lane:
        p = _lane_path(lane) / filename
        return p.read_text(encoding="utf-8") if p.exists() else f"Not found: {filename}"
    for folder in LANES.values():
        p = VAULT_ROOT / folder / filename
        if p.exists():
            return p.read_text(encoding="utf-8")
    return f"Not found: {filename}"

def search_notes(query, lane=None):
    results = []
    q = query.lower()
    search_lanes = [LANES[lane]] if lane and lane in LANES else list(LANES.values())
    for folder in search_lanes:
        p = VAULT_ROOT / folder
        if not p.exists():
            continue
        for f in p.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            if q in text.lower():
                idx = text.lower().find(q)
                start = max(0, idx - 80)
                end = min(len(text), idx + 120)
                excerpt = text[start:end].replace("\n", " ").strip()
                results.append({"file": f.name, "lane": folder, "excerpt": f"...{excerpt}..."})
    return results

def list_notes(lane=None, limit=20):
    files = []
    search_lanes = [LANES[lane]] if lane and lane in LANES else list(LANES.values())
    for folder in search_lanes:
        p = VAULT_ROOT / folder
        if not p.exists():
            continue
        for f in p.glob("*.md"):
            files.append((f.stat().st_mtime, f.name, folder))
    files.sort(reverse=True)
    return [{"file": f, "lane": l} for _, f, l in files[:limit]]

def vault_summary():
    total = 0
    by_lane = {}
    for name, folder in LANES.items():
        p = VAULT_ROOT / folder
        count = len(list(p.glob("*.md"))) if p.exists() else 0
        by_lane[name] = count
        total += count
    return {"vault_root": str(VAULT_ROOT), "total_notes": total, "by_lane": by_lane}

if __name__ == "__main__":
    print(json.dumps(vault_summary(), indent=2))
