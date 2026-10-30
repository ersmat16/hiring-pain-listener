"""Hacker News through the free Algolia search API. No key.

Dense with founders and CTOs. Profiles have an optional "about" field that often
names the person's company, which helps the ICP check.
"""
from __future__ import annotations

import html
import re
import time

from ..http import get_json
from ..models import Person, Post, SourceStatus

ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _about(user: str, cache: dict) -> str:
    if user not in cache:
        try:
            cache[user] = _clean((get_json(f"{FIREBASE}/user/{user}.json") or {}).get("about", ""))[:400]
        except Exception:
            cache[user] = ""
    return cache[user]


def hit_to_post(h: dict, about: str = "") -> Post:
    text = _clean(h.get("story_text") or h.get("comment_text") or "")
    oid = h["objectID"]
    author = Person(platform="hackernews", handle=h.get("author", ""), bio=about,
                    profile_url=f"https://news.ycombinator.com/user?id={h.get('author', '')}",
                    said=text[:500], is_author=True)
    return Post(platform="hackernews", id=oid, url=f"https://news.ycombinator.com/item?id={oid}",
                title=h.get("title") or h.get("story_title") or "", text=text, author=author,
                created_at=h.get("created_at", ""), community="Hacker News",
                likes=h.get("points") or 0, replies_count=h.get("num_comments") or 0)


def replies(post: Post, limit: int, cache: dict) -> list[Person]:
    try:
        item = get_json(f"{ALGOLIA}/items/{post.id}")
    except Exception:
        return []
    out = []
    for c in (item.get("children") or [])[:limit]:
        if c.get("author") and c.get("text"):
            out.append(Person(platform="hackernews", handle=c["author"], bio=_about(c["author"], cache),
                              profile_url=f"https://news.ycombinator.com/user?id={c['author']}",
                              said=_clean(c["text"])[:500]))
    return out


def fetch(cfg: dict, cache: dict) -> tuple[list[Post], SourceStatus]:
    sc = cfg["sources"]["hackernews"]
    if not sc.get("enabled"):
        return [], SourceStatus("Hacker News", "disabled")
    since = int(time.time()) - cfg["lookback_hours"] * 3600
    posts, seen, errors = [], set(), 0
    for q in cfg["keywords"]:
        try:
            res = get_json(f"{ALGOLIA}/search_by_date",
                           {"query": q, "tags": "(story,comment)", "numericFilters": f"created_at_i>{since}",
                            "hitsPerPage": sc["per_query"]})
        except Exception:
            errors += 1
            continue
        for h in res.get("hits", []):
            if h["objectID"] not in seen:
                seen.add(h["objectID"])
                posts.append(hit_to_post(h, _about(h.get("author", ""), cache)))
    if errors == len(cfg["keywords"]):
        return [], SourceStatus("Hacker News", "failed", "Every request failed. Check the network.")
    return posts, SourceStatus("Hacker News", "ran", found=len(posts))
