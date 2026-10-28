"""Discover new RSS items; initial run baselines old episodes to avoid historical backfill."""
import json
from pathlib import Path
from datetime import datetime, timezone
import feedparser

FEEDS = json.loads(Path("config/feeds.json").read_text(encoding="utf-8"))
OUT = Path("queue/state.json")
OUT.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"feeds": {}, "pending": []}
state.setdefault("feeds", {})
state.setdefault("pending", [])
known = {row["key"] for row in state["pending"]}
for feed in FEEDS:
    if not feed.get("enabled"): continue
    parsed = feedparser.parse(feed["rss"], request_headers={"User-Agent": "PodcastMonitor/0.2"})
    if not parsed.entries:
        raise RuntimeError("RSS returned no entries: " + feed["id"])
    fid = feed["id"]
    ids = [str(entry.get("id") or entry.get("link") or "") for entry in parsed.entries]
    if fid not in state["feeds"]:
        state["feeds"][fid] = sorted(set(ids))
        print(f"{fid}: initialized baseline {len(ids)}")
        continue
    seen = set(state["feeds"][fid])
    unique_entries = {}
    for item in parsed.entries:
        uid = str(item.get("id") or item.get("link") or "")
        unique_entries.setdefault(uid, item)
    for item in reversed(list(unique_entries.values())):
        uid = str(item.get("id") or item.get("link") or "")
        if not uid or uid in seen or fid + ":" + uid in known: continue
        key = fid + ":" + uid
        audio = next((e.get("href") for e in item.get("enclosures", []) if e.get("href")), "")
        state["pending"].append({"key": key, "feed_id": fid,
            "feed_name": feed["name"], "guid": uid,
            "title": item.get("title", ""), "url": item.get("link", ""),
            "audio_url": audio,
            "published": item.get("published", ""),
            "rss_duration": item.get("itunes_duration", ""),
            "detected_at": datetime.now(timezone.utc).isoformat()})
        known.add(key)
    state["feeds"][fid] = sorted(seen.union(ids))
tmp = OUT.with_suffix(".tmp")
tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
tmp.replace(OUT)
print("Total queued episodes:", len(state["pending"]))
