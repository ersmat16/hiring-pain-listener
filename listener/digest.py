"""Writes the daily digest: Act on, Use in content, Also read, People, and source status."""
from __future__ import annotations

from datetime import datetime

from .models import Post, SourceStatus

PLATFORM = {"reddit": "Reddit", "hackernews": "Hacker News", "x": "X", "linkedin": "LinkedIn"}


def _post_detail(i: int, p: Post) -> list[str]:
    s = p.scores
    title = p.title or (p.text[:80] + ("..." if len(p.text) > 80 else ""))
    lines = [f"### {i}. {title}", "",
             f"- **Where:** {PLATFORM.get(p.platform, p.platform)}"
             f"{' · ' + p.community if p.community and p.community != PLATFORM.get(p.platform) else ''}"
             f" · [open]({p.url}) · {p.likes:,} likes" + (f" · {p.views:,} views" if p.views else ""),
             f"- **Scores:** fit {s.get('fit')}, author {s.get('author')}, reach {s.get('reach')}, "
             f"freshness {s.get('freshness')} · **Campaign:** {p.campaign}"]
    if p.risk and p.risk.lower() != "none":
        lines.append(f"- **Risk:** {p.risk}")
    if p.quote:
        lines.append(f"- **Quote:** \"{p.quote}\"")
    if p.seb_angle:
        lines.append(f"- **Angle:** {p.seb_angle}")
    if p.ad_hook:
        lines.append(f"- **Ad hook:** {p.ad_hook}")
    lines.append("")
    return lines


def build(posts: list[Post], statuses: list[SourceStatus], cfg: dict,
          sample: bool = False, unscored: int = 0) -> tuple[str, list[dict]]:
    th = cfg["thresholds"]

    act     = [p for p in posts if p.use == "act"]
    content = [p for p in posts if p.use == "content"]
    skip    = [p for p in posts if p.use == "skip"]

    people = []
    for p in act + content:
        for person in [p.author, *p.replies]:
            if person.stance == "agrees" and person.icp_fit >= th["people_min_icp"]:
                people.append({"person": person, "post": p})

    out = [f"# Hiring pain digest, {datetime.now():%A %d %B %Y}", ""]

    if sample:
        out += ["> **Sample run.** Built from saved example posts in `fixtures/`, not a live search. "
                "Replies marked SAMPLE are invented test data, not real people.", ""]

    scorer_names = {p.scored_by for p in posts if p.scored_by} or {"none"}
    summary = (f"Read {len(posts)} {'post' if len(posts) == 1 else 'posts'} · "
               f"{len(act)} to act on · {len(content)} for content · {len(skip)} skipped · "
               f"scored by {', '.join(sorted(scorer_names))}")
    if unscored:
        summary += f" · {unscored} {'post' if unscored == 1 else 'posts'} dropped (scoring failed)"
    out += [summary, ""]

    out += ["## Act on", ""]
    if not act:
        out += ["Nothing to act on today.", ""]
    for i, p in enumerate(act, 1):
        out += _post_detail(i, p)

    out += ["## Use in content", ""]
    if not content:
        out += ["Nothing for content today.", ""]
    for i, p in enumerate(content, 1):
        out += _post_detail(i, p)

    out += ["## Also read", ""]
    if not skip:
        out += ["Nothing else today.", ""]
    for p in skip:
        title = p.title or (p.text[:80] + ("..." if len(p.text) > 80 else ""))
        out.append(f"- [{title}]({p.url}){' — ' + p.use_why if p.use_why else ''}")
    out.append("")

    out += ["## People: ICP fits in these conversations", ""]
    if people:
        out += ["| Who | Role and company | Fit | What they said | Where |",
                "| --- | --- | --- | --- | --- |"]
        for row in people:
            pr, po = row["person"], row["post"]
            who = f"[{pr.name or pr.handle}]({pr.profile_url})" if pr.profile_url else (pr.name or pr.handle)
            if pr.is_author:
                who += " (posted)"
            said = pr.said[:140].replace("|", "/") + ("..." if len(pr.said) > 140 else "")
            rc = ", ".join(x for x in [pr.role, pr.company] if x and x != "unknown") or "unknown"
            out.append(f"| {who} | {rc} | {pr.icp_fit} | {said} | [{PLATFORM.get(po.platform, po.platform)}]({po.url}) |")
        out += ["", "Follow up with something useful that matches what they said. Never mention their post.", ""]
    else:
        out += ["No ICP fits today.", ""]

    out += ["## Sources", "", "| Source | Status | Found | Notes |", "| --- | --- | --- | --- |"]
    label = {"ready": "Ready (free)", "ran": "Ran", "needs_access": "Needs access", "failed": "Failed", "disabled": "Off"}
    for st in statuses:
        note = st.detail + (f" Unlocks: {st.unlocks}" if st.state == "needs_access" and st.unlocks else "")
        out.append(f"| {st.name} | {label.get(st.state, st.state)} | {st.found} | {note.strip()} |")
    out.append("")

    sdr_rows = [{
        "name": r["person"].name, "handle": r["person"].handle, "platform": r["person"].platform,
        "profile_url": r["person"].profile_url, "role": r["person"].role, "company": r["person"].company,
        "icp_fit": r["person"].icp_fit, "said": r["person"].said, "post_url": r["post"].url,
        "campaign": r["post"].campaign,
    } for r in people]
    return "\n".join(out), sdr_rows
