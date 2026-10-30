"""Run the listener: fetch, check people, score, write the digest.

    python -m listener.run            # live run on every source you have access to
    python -m listener.run --sample   # demo on saved example posts, no network needed
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import yaml

from . import clay, digest, scorer, slack
from .models import Post, SourceStatus
from .sources import hackernews, octolens, reddit, x

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def fetch_all(cfg: dict) -> tuple[list[Post], list[SourceStatus], dict]:
    hn_cache: dict = {}
    posts, statuses = [], []
    for name, fn in [("reddit", lambda: reddit.fetch(cfg)), ("hn", lambda: hackernews.fetch(cfg, hn_cache)),
                     ("x", lambda: x.fetch(cfg)), ("octolens", lambda: octolens.fetch(cfg))]:
        found, status = fn()
        posts += found
        statuses.append(status)
        print(f"  {status.name}: {status.state}, {status.found} posts")
    return posts, statuses, hn_cache


def add_replies(posts: list[Post], cfg: dict, hn_cache: dict) -> None:
    n = cfg["thresholds"]["max_replies_per_post"]
    for p in posts:
        if p.platform == "reddit":
            p.replies = reddit.replies(p, n)
        elif p.platform == "hackernews":
            p.replies = hackernews.replies(p, n, hn_cache)
        elif p.platform == "x" and os.environ.get("X_BEARER_TOKEN"):
            p.replies = x.replies(p, n)
        # Octolens replies: confirm in the trial whether its API returns them.


def sample_statuses() -> list[SourceStatus]:
    st = [SourceStatus("Reddit", "ready", "No key needed. Runs live without --sample."),
          SourceStatus("Hacker News", "ready", "No key needed. Runs live without --sample.")]
    if not os.environ.get("X_BEARER_TOKEN"):
        st.append(SourceStatus("X", "needs_access", "Add X_BEARER_TOKEN (pay per use).",
                               unlocks="Founders and CTOs under their real names, with bios and replies."))
    if not os.environ.get("OCTOLENS_API_KEY"):
        st.append(SourceStatus("Octolens (LinkedIn and more)", "needs_access", "Add OCTOLENS_API_KEY (paid).",
                               unlocks="LinkedIn posts with names, titles and companies, plus podcasts and reviews."))
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description="Find hiring-pain posts and the ICP people in them.")
    ap.add_argument("--sample", action="store_true", help="use fixtures/sample_posts.json instead of live sources")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--out", default=str(ROOT / "output"))
    args = ap.parse_args()

    load_env(ROOT / ".env")
    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.sample:
        print("Sample run: loading saved example posts")
        posts = [Post.from_dict(d) for d in json.loads((ROOT / "fixtures" / "sample_posts.json").read_text())]
        statuses = sample_statuses()
    else:
        print("Listening")
        posts, statuses, hn_cache = fetch_all(cfg)
        posts = scorer.prefilter(posts, cfg["thresholds"]["max_posts_to_score"])
        print(f"Checking replies on {len(posts)} posts")
        add_replies(posts, cfg, hn_cache)

    client = scorer.make_client()
    print(f"Scoring {len(posts)} posts with {'Claude' if client else 'the keyword fallback (no ANTHROPIC_API_KEY)'}")
    unscored = 0
    for i, p in enumerate(posts):
        if i > 0:
            time.sleep(2)
        try:
            scorer.claude_score(p, cfg, client) if client else scorer.keyword_score(p)
        except Exception as e:
            print(f"  {'Claude' if client else 'Keyword scorer'} failed on {p.url} ({type(e).__name__}: {e}); skipping")
            unscored += 1
    if not client:
        statuses.append(SourceStatus("Claude (scoring)", "needs_access", "Add ANTHROPIC_API_KEY.",
                                     unlocks="Real judgement on fit, ICP and risk, plus drafted Seb angles and ad hooks."))

    md, sdr_rows = digest.build(posts, statuses, cfg, sample=args.sample, unscored=unscored)
    if sdr_rows and not args.sample:
        statuses.append(clay.send(sdr_rows))
        md, sdr_rows = digest.build(posts, statuses, cfg, sample=args.sample, unscored=unscored)
    elif not os.environ.get("CLAY_WEBHOOK_URL"):
        statuses.append(clay.send([]))
        md, sdr_rows = digest.build(posts, statuses, cfg, sample=args.sample, unscored=unscored)

    stamp = datetime.now().strftime("%Y-%m-%d")
    (out / f"digest-{stamp}.md").write_text(md)
    (out / f"posts-{stamp}.json").write_text(json.dumps([p.to_dict() for p in posts], indent=2))
    with open(out / f"people-{stamp}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "handle", "platform", "profile_url", "role", "company",
                                          "icp_fit", "said", "post_url", "campaign"])
        w.writeheader()
        w.writerows(sdr_rows)
    slack.send(posts, sdr_rows, statuses, cfg)
    print(f"Done: {out / f'digest-{stamp}.md'}")


if __name__ == "__main__":
    main()
