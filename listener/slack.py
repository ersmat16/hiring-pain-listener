"""Post a short summary to Slack via an incoming webhook. Optional; skipped if no URL is set."""
from __future__ import annotations

import json
import os
import urllib.request

from .models import Post, SourceStatus


def _post_block(i: int, p: Post) -> str:
    title = p.title or (p.text[:80] + ("…" if len(p.text) > 80 else ""))
    lines = [f"*{i}. <{p.url}|{title}>*  ·  campaign: {p.campaign}"]
    if p.ad_hook:
        lines.append(f"_{p.ad_hook}_")
    return "\n".join(lines)


def send(posts: list[Post], sdr_rows: list[dict], statuses: list[SourceStatus], cfg: dict) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return

    th = cfg["thresholds"]
    content = sorted(
        [p for p in posts if p.scores.get("fit", 0) >= th["content_min_fit"]],
        key=lambda p: sum(p.scores.values()),
        reverse=True,
    )[:3]

    blocks: list[str] = []

    if content:
        blocks.append(f"*{len(content)} post{'s' if len(content) != 1 else ''} worth using today*")
        for i, p in enumerate(content, 1):
            blocks.append(_post_block(i, p))
    else:
        blocks.append("*No posts cleared the bar today.*")

    if sdr_rows:
        names = ", ".join(
            f"{r['name'] or r['handle']} ({r['role'] or 'unknown'})" for r in sdr_rows
        )
        blocks.append(f"*{len(sdr_rows)} ICP fit{'s' if len(sdr_rows) != 1 else ''}:* {names}")
    else:
        blocks.append("*0 ICP fits today.*")

    needs = [st.name for st in statuses if st.state == "needs_access"]
    if needs:
        blocks.append(f"Sources needing access: {', '.join(needs)}")

    payload = {"text": "\n\n".join(blocks)}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Slack delivery is best-effort; never break the run
