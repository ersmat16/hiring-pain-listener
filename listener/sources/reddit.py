"""Reddit through its public search RSS feeds. Free, no key.

Reddit is great for honest content but mostly anonymous, so ICP fit can only come
from clues in the post itself. Check Reddit's terms before any commercial use.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET

from ..http import get
from ..models import Person, Post, SourceStatus

ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _clean(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"submitted by /u/\S+ \[link\] \[comments\]$", "", s).strip()


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall("a:entry", ATOM):
        link = e.find("a:link", ATOM)
        author = e.find("a:author/a:name", ATOM)
        out.append({
            "id": (e.findtext("a:id", default="", namespaces=ATOM)),
            "title": e.findtext("a:title", default="", namespaces=ATOM),
            "url": link.get("href") if link is not None else "",
            "text": _clean(e.findtext("a:content", default="", namespaces=ATOM)),
            "author": (author.text or "").replace("/u/", "") if author is not None else "",
            "created_at": e.findtext("a:published", default="", namespaces=ATOM)
                          or e.findtext("a:updated", default="", namespaces=ATOM),
            "community": (e.find("a:category", ATOM).get("term") if e.find("a:category", ATOM) is not None else ""),
        })
    return out


def _to_post(d: dict, sub: str) -> Post:
    author = Person(platform="reddit", handle=d["author"], profile_url=f"https://www.reddit.com/user/{d['author']}",
                    said=d["text"][:500], is_author=True)
    return Post(platform="reddit", id=d["id"], url=d["url"], title=d["title"], text=d["text"],
                author=author, created_at=d["created_at"], community=d["community"] or sub)


def replies(post: Post, limit: int) -> list[Person]:
    """The comments feed is the post URL + .rss; its first entry is the post itself."""
    try:
        entries = parse_feed(get(post.url.rstrip("/") + "/.rss"))[1:limit + 1]
    except Exception:
        return []
    return [Person(platform="reddit", handle=c["author"], profile_url=f"https://www.reddit.com/user/{c['author']}",
                   said=c["text"][:500]) for c in entries if c["author"]]


def fetch(cfg: dict) -> tuple[list[Post], SourceStatus]:
    sc = cfg["sources"]["reddit"]
    if not sc.get("enabled"):
        return [], SourceStatus("Reddit", "disabled")
    posts, seen, errors = [], set(), 0
    for sub in sc["subreddits"]:
        for q in cfg["keywords"]:
            time.sleep(1.5)  # stay well under Reddit's rate limit for unauthenticated feeds
            try:
                feed = get(f"https://www.reddit.com/r/{sub}/search.rss",
                           {"q": q, "restrict_sr": 1, "sort": "new", "t": "week", "limit": sc["per_query"]})
            except Exception:
                errors += 1
                continue
            for d in parse_feed(feed):
                if d["id"] not in seen and d["author"]:
                    seen.add(d["id"])
                    posts.append(_to_post(d, sub))
    total = len(sc["subreddits"]) * len(cfg["keywords"])
    if errors == total:
        return [], SourceStatus("Reddit", "failed", "Every request failed. Check the network, or Reddit may be rate limiting.")
    return posts, SourceStatus("Reddit", "ran", f"{len(sc['subreddits'])} subreddits", found=len(posts))
