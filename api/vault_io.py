import os, tempfile, uuid, re
from datetime import datetime, timezone
import frontmatter

VAULT_ROOT = os.environ.get("VAULT_PATH", "/vault")

LANES = {
    "inbox":    "00-inbox",
    "research": "10-research",
    "deals":    "20-deals",
    "beta":     "25-beta-leads",
    "surplus":  "30-surplus-cases",
    "manual":   "40-manual",
    "meta":     "90-meta",
    "health":   "_health",
}

def _lane_path(lane):
    return os.path.join(VAULT_ROOT, LANES.get(lane, lane))

def write_note_atomic(path, content, metadata):
    """Atomic write — safe under concurrent agent writes."""
    post = frontmatter.Post(content, **metadata)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            frontmatter.dump(post, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def create_note(lane, title, content, agent, note_type, tags=None, extra_meta=None):
    """Create a note in the given lane. Returns the path written."""
    ts = datetime.now(timezone.utc)
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower())[:40].strip('-')
    uid = str(uuid.uuid4())[:8]
    filename = f"{ts.strftime('%Y-%m-%d')}_{slug}_{uid}.md"
    path = os.path.join(_lane_path(lane), filename)
    metadata = {
        "type": note_type,
        "title": title,
        "created": ts.isoformat(),
        "agent": agent,
        "status": "raw",
        "tags": tags or [],
    }
    if extra_meta:
        metadata.update(extra_meta)
    write_note_atomic(path, content, metadata)
    return path

def read_note(path):
    """Returns (metadata_dict, content_str)."""
    post = frontmatter.load(path)
    return dict(post.metadata), post.content

def update_status(path, status):
    """Update the status field of an existing note in-place."""
    post = frontmatter.load(path)
    post["status"] = status
    write_note_atomic(path, post.content, dict(post.metadata))

def list_lane(lane, status_filter=None):
    """List notes in a lane, optionally filtered by status."""
    lane_dir = _lane_path(lane)
    if not os.path.isdir(lane_dir):
        return []
    results = []
    for fname in sorted(os.listdir(lane_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(lane_dir, fname)
        try:
            post = frontmatter.load(path)
            meta = dict(post.metadata)
            if status_filter and meta.get("status") != status_filter:
                continue
            results.append({"path": path, "filename": fname, **meta})
        except Exception:
            pass
    return results
