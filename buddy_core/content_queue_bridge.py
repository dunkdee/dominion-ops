#!/usr/bin/env python3
"""
content_queue_bridge.py — Bridge between content_batch_*.json and content_queue/
Converts daily batch format into the slot-based .txt files social_poster.py reads.

Run before social_poster.py. Cron: 30 min before each social post slot.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path("/home/malachisingleton8/buddy_core")
BATCH_DIR = HOME
QUEUE_DIR = Path.home() / "content_queue"

def get_batch(date_str):
    """Load content batch for a given YYYYMMDD date string."""
    path = BATCH_DIR / f"content_batch_{date_str}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None

def populate_queue(date_str=None):
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y%m%d")
    
    today_dash = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    
    batch = get_batch(date_str)
    if not batch:
        print(f"No batch found for {date_str}")
        return 0
    
    content = batch.get("content", {})
    social_posts = content.get("social_posts", [])
    
    # Platform mapping: batch name → queue subdir name(s)
    PLATFORM_MAP = {
        "facebook":  ["facebook"],
        "twitter":   ["twitter"],
        "instagram": ["instagram"],
        "tiktok":    ["tiktok"],
        "linkedin":  ["linkedin"],
        "youtube":   ["youtube"],
        "reddit":    ["reddit"],
        "medium":    ["medium"],
    }
    
    # Collect posts per platform
    platform_posts = {}
    for post in social_posts:
        platforms = post.get("platforms", [])
        # content field can be str or dict
        c = post.get("content", "")
        if isinstance(c, dict):
            text = c.get("text", c.get("body", str(c)))
        else:
            text = str(c)
        
        # Append CTA if not already in text
        cta = post.get("cta", "")
        if cta and cta not in text:
            text = f"{text}\n\n{cta}"
        
        for plat in platforms:
            plat_lower = plat.lower()
            if plat_lower not in platform_posts:
                platform_posts[plat_lower] = []
            platform_posts[plat_lower].append(text.strip())
    
    # Also pull from short_videos for tiktok/youtube/instagram
    for vid in content.get("short_videos", []):
        plats = vid.get("platform", [])
        script = vid.get("script", "")
        hook = vid.get("hook", "")
        cta = vid.get("cta", "")
        text = f"{hook}\n\n{script}"
        if cta and cta not in text:
            text += f"\n\n{cta}"
        for plat in plats:
            plat_lower = plat.lower().replace("_reels","").replace("_shorts","")
            if plat_lower not in platform_posts:
                platform_posts[plat_lower] = []
            platform_posts[plat_lower].append(text.strip())
    
    written = 0
    for plat, posts in platform_posts.items():
        queue_subdir = QUEUE_DIR / plat
        queue_subdir.mkdir(parents=True, exist_ok=True)
        
        for slot, text in enumerate(posts):
            # Write slot file
            slot_f = queue_subdir / f"{today_dash}_slot{slot}.txt"
            if not slot_f.exists():
                slot_f.write_text(text, encoding="utf-8")
                written += 1
        
        # Write main daily file (first post)
        main_f = queue_subdir / f"{today_dash}.txt"
        if not main_f.exists() and posts:
            main_f.write_text(posts[0], encoding="utf-8")
            written += 1
        
        print(f"  {plat}: {len(posts)} slots written to {queue_subdir}")
    
    return written

if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"Content Queue Bridge — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    n = populate_queue(date_arg)
    print(f"Done. {n} files written to {QUEUE_DIR}")
