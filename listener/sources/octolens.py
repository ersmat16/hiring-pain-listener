"""Octolens: one paid connection for LinkedIn, X, Reddit, Hacker News, podcasts, newsletters and reviews.

Needs OCTOLENS_API_KEY. Octolens documents a REST endpoint (POST /api/v2/mentions),
webhooks and an MCP server. The request and response field names below are a best
guess: confirm them against Octolens's API docs during the free trial and adjust
FIELD_MAP. Nothing else in the project needs to change.
"""
from __future__ import annotations

import os

from ..http import post_json
from ..models import Person, Post, SourceStatus

# Where each of our fields lives in an Octolens mention. Adjust after checking the docs.
FIELD_MAP = {
    "id": ["id"],
    "url": ["url", "link"],
    "text": ["body", "text", "content"],
    "title": ["title"],
    "platform": ["source", "platform"],
    "created_at": ["timestamp", "createdAt", "created_at"],
    "author_handle": ["author.username", "author.handle", "author"],
    "author_name": ["author.name", "authorName"],
    "author_bio": ["author.bio", "author.headline", "author.description"],
    "author_url": ["author.profileUrl", "author.url", "authorProfileLink"],
    "likes": ["engagement.likes", "likes"],
}


def _pick(d: dict, paths: list[str]):
    for p in paths:
        cur = d
        for k in p.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur not in (None, "") and not isinstance(cur, dict):
            return cur
    return ""


def mention_to_post(m: dict) -> Post:
    g = lambda k: _pick(m, FIELD_MAP[k])
    platform = str(g("platform") or "octolens").lower()
    author = Person(platform=platform, handle=str(g("author_handle")), name=str(g("author_name")),
                    bio=str(g("author_bio")), profile_url=str(g("author_url")), said=str(g("text"))[:500],
                    is_author=True)
    return Post(platform=platform, id=str(g("id")), url=str(g("url")), text=str(g("text")), title=str(g("title")),
                author=author, created_at=str(g("created_at")), likes=int(g("likes") or 0))


def fetch(cfg: dict) -> tuple[list[Post], SourceStatus]:
    sc = cfg["sources"]["octolens"]
    unlocks = "LinkedIn posts with real names, titles and companies, plus podcasts, newsletters and competitor reviews."
    if not sc.get("enabled"):
        return [], SourceStatus("Octolens (LinkedIn and more)", "disabled")
    key = os.environ.get("OCTOLENS_API_KEY", "")
    if not key:
        return [], SourceStatus("Octolens (LinkedIn and more)", "needs_access",
                                "Add OCTOLENS_API_KEY (paid; 7-day free trial).", unlocks=unlocks)
    url = os.environ.get("OCTOLENS_API_URL", "https://app.octolens.com/api/v2/mentions")
    try:
        res = post_json(url, {"limit": sc["limit"], "includeAll": False}, {"Authorization": f"Bearer {key}"})
    except Exception as e:
        return [], SourceStatus("Octolens (LinkedIn and more)", "failed", f"Octolens API error: {e}")
    items = res.get("data") or res.get("mentions") or (res if isinstance(res, list) else [])
    posts = [mention_to_post(m) for m in items]
    return posts, SourceStatus("Octolens (LinkedIn and more)", "ran", found=len(posts))
