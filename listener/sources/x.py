"""X through its official API (v2 recent search). Needs X_BEARER_TOKEN.

X moved to pay-per-use in 2026: roughly $0.005 per post read and $0.01 per profile.
Check current rates in the X Developer Console before relying on them.
"""
from __future__ import annotations

import os

from ..http import get_json
from ..models import Person, Post, SourceStatus

API = "https://api.x.com/2/tweets/search/recent"
FIELDS = {
    "tweet.fields": "created_at,public_metrics,author_id,conversation_id",
    "expansions": "author_id",
    "user.fields": "name,username,description",
}


def _token() -> str:
    return os.environ.get("X_BEARER_TOKEN", "")


def _people(res: dict) -> dict:
    return {u["id"]: u for u in (res.get("includes") or {}).get("users", [])}


def _person(u: dict, said: str, is_author: bool = False) -> Person:
    return Person(platform="x", handle=u.get("username", ""), name=u.get("name", ""), bio=u.get("description", ""),
                  profile_url=f"https://x.com/{u.get('username', '')}", said=said[:500], is_author=is_author)


def _search(query: str, n: int) -> dict:
    return get_json(API, {"query": query, "max_results": max(10, min(100, n)), **FIELDS},
                    {"Authorization": f"Bearer {_token()}"})


def results_to_posts(res: dict, min_likes: int) -> list[Post]:
    users, out = _people(res), []
    for t in res.get("data", []):
        m = t.get("public_metrics", {})
        if m.get("like_count", 0) < min_likes:
            continue
        u = users.get(t["author_id"], {"id": t["author_id"]})
        out.append(Post(platform="x", id=t["id"], url=f"https://x.com/{u.get('username', 'i')}/status/{t['id']}",
                        text=t["text"], author=_person(u, t["text"], True), created_at=t.get("created_at", ""),
                        likes=m.get("like_count", 0), replies_count=m.get("reply_count", 0),
                        views=m.get("impression_count", 0)))
    return out


def replies(post: Post, limit: int) -> list[Person]:
    try:
        res = _search(f"conversation_id:{post.id} -is:retweet", limit)
    except Exception:
        return []
    users = _people(res)
    return [_person(users.get(t["author_id"], {}), t["text"]) for t in res.get("data", [])
            if t["author_id"] in users and t["id"] != post.id][:limit]


def fetch(cfg: dict) -> tuple[list[Post], SourceStatus]:
    sc = cfg["sources"]["x"]
    unlocks = "Founders and CTOs posting under their real names, with bios for the ICP check, and their replies."
    if not sc.get("enabled"):
        return [], SourceStatus("X", "disabled")
    if not _token():
        return [], SourceStatus("X", "needs_access", "Add X_BEARER_TOKEN from the X Developer Console (pay per use).",
                                unlocks=unlocks)
    posts, seen = [], set()
    try:
        for q in cfg["keywords"]:
            for p in results_to_posts(_search(f"({q}) lang:en -is:retweet", sc["per_query"]), sc["min_likes"]):
                if p.id not in seen:
                    seen.add(p.id)
                    posts.append(p)
    except Exception as e:
        return posts, SourceStatus("X", "failed", f"X API error: {e}", found=len(posts))
    return posts, SourceStatus("X", "ran", found=len(posts))
