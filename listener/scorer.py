"""Scores posts and people. Uses Claude when ANTHROPIC_API_KEY is set, else a basic keyword fallback."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from .models import Person, Post

INSTRUCTION = """You review social posts for this company:
{company}

Its ideal customer (ICP):
{icp}

Campaigns a post can support:
{campaigns}

Score the post and the people in it. Reply with only JSON in exactly this shape:
{{
  "post": {{
    "fit": 1-5,          "author": 1-5,   "reach": 1-5,   "freshness": 1-5,
    "campaign": one of {campaign_keys},
    "risk": "none" or one short line,
    "quote": the strongest sentence from the post, verbatim,
    "seb_angle": two sentences giving the founder's point of view in reaction. Never a pitch,
    "ad_hook": under 12 words
  }},
  "people": [
    {{"handle": "...", "stance": "agrees|neutral|disagrees", "role": "...", "company": "...",
      "icp_fit": 1-5, "reason": "one short line"}}
  ]
}}

Rules:
- fit: 5 means the post states a pain the company solves directly. 1 means loosely about hiring.
- author: 5 means a founder, CTO or engineering leader. 1 means anonymous or a job seeker.
- reach: use likes, replies and views. 5 means 100k+ views or a top post in a large community.
- freshness: 5 means under 24 hours old, 1 means over a month.
- Flag risk when a post insults a group of engineers (for example by country), names a private person,
  or involves a job seeker's distress.
- Judge each person's role and company only from their bio and what they wrote. If unknown, say "unknown"
  and score icp_fit 2 or lower. Do not guess employers.
- Include every person listed, the author first.

Post ({platform}, {community}, posted {created_at}, {likes} likes, {replies_count} replies, {views} views):
Title: {title}
{text}

People:
{people}
"""

ROLE_RE = re.compile(r"\b(co-?founder|founder|cto|chief technology|vp,? (of )?eng|head of (engineering|product|tech)|"
                     r"engineering (manager|director|lead)|ceo)\b", re.I)
PAIN_RE = re.compile(r"\b(applicants?|applications|resumes?|cvs?|cheat|deepfake|fake candidates?|interview loop|"
                     r"months to (hire|fill)|can'?t (find|hire)|recruiter fee|tailored|senior)\b", re.I)
AGREE_RE = re.compile(r"\b(same|we had|we got|agree|exactly|this\.|so true|happened to us|our experience|"
                      r"we're seeing|we are seeing|\+1)\b", re.I)


def _hours_old(ts: str) -> float:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 9999


def keyword_score(post: Post) -> Post:
    text = f"{post.title} {post.text}"
    hits = len(PAIN_RE.findall(text))
    reach = max(post.likes, post.views // 50)
    age = _hours_old(post.created_at)
    post.scores = {
        "fit": min(5, 2 + hits),
        "author": 4 if ROLE_RE.search(post.author.bio + " " + text[:200]) else 2,
        "reach": 5 if reach >= 2000 else 4 if reach >= 500 else 3 if reach >= 100 else 2 if reach >= 20 else 1,
        "freshness": 5 if age < 24 else 4 if age < 72 else 3 if age < 168 else 2 if age < 720 else 1,
    }
    post.campaign = "senior-on-paper" if re.search(r"resume|cv|cheat|fake|tailored|can'?t code", text, re.I) else "find-them"
    post.risk = "none"
    sentences = re.split(r"(?<=[.!?])\s+", post.text)
    post.quote = max(sentences, key=lambda s: len(PAIN_RE.findall(s)), default="")[:240]
    post.scored_by = "keywords"
    for p in [post.author, *post.replies]:
        p.stance = "agrees" if p.is_author or AGREE_RE.search(p.said) else "neutral"
        m = ROLE_RE.search(p.bio)
        p.role = m.group(0) if m else "unknown"
        p.icp_fit = 4 if m else 1
        p.reason = "Role found in profile" if m else "No role in profile"
    return post


def _people_block(post: Post) -> str:
    lines = []
    for p in [post.author, *post.replies]:
        tag = "AUTHOR" if p.is_author else "REPLY"
        lines.append(f"- [{tag}] handle={p.handle} name={p.name or '-'} bio={p.bio or '-'} said={p.said[:300]}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def claude_score(post: Post, cfg: dict, client) -> Post:
    prompt = INSTRUCTION.format(
        company=cfg["company"].strip(), icp=cfg["icp"].strip(),
        campaigns="\n".join(f"- {k}: {v}" for k, v in cfg["campaigns"].items()),
        campaign_keys=" | ".join(cfg["campaigns"].keys()),
        platform=post.platform, community=post.community or "-", created_at=post.created_at or "unknown",
        likes=post.likes, replies_count=post.replies_count, views=post.views or "unknown",
        title=post.title or "-", text=post.text[:4000], people=_people_block(post),
    )
    msg = client.messages.create(model=cfg["model"], max_tokens=1500, messages=[{"role": "user", "content": prompt}])
    data = _parse_json("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
    pd = data.get("post", {})
    post.scores = {k: int(pd.get(k, 0) or 0) for k in ("fit", "author", "reach", "freshness")}
    post.campaign, post.risk = pd.get("campaign", ""), pd.get("risk", "none")
    post.quote, post.seb_angle, post.ad_hook = pd.get("quote", ""), pd.get("seb_angle", ""), pd.get("ad_hook", "")
    post.scored_by = "claude"
    by_handle = {x.get("handle"): x for x in data.get("people", [])}
    for p in [post.author, *post.replies]:
        x = by_handle.get(p.handle, {})
        p.stance, p.role, p.company = x.get("stance", "neutral"), x.get("role", ""), x.get("company", "")
        p.icp_fit, p.reason = int(x.get("icp_fit", 0) or 0), x.get("reason", "")
    return post


def make_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()


def prefilter(posts: list[Post], limit: int) -> list[Post]:
    """Cheap first pass so Claude only sees the most promising posts."""
    def rank(p: Post):
        return (len(PAIN_RE.findall(f"{p.title} {p.text}")), p.likes + p.replies_count)
    return sorted(posts, key=rank, reverse=True)[:limit]
