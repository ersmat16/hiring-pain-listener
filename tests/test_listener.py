"""Offline tests: every source's parsing, both scorers, and the digest. Run: python -m unittest -v"""
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from listener import digest, scorer
from listener.models import Person, Post
from listener.sources import hackernews, octolens, reddit, x

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())

REDDIT_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <author><name>/u/tired_cto</name></author>
    <category term="startups" label="r/startups"/>
    <content type="html">&lt;p&gt;We got 900 applicants for one role and every resume matched our stack.&lt;/p&gt; submitted by /u/tired_cto [link] [comments]</content>
    <id>t3_abc123</id>
    <link href="https://www.reddit.com/r/startups/comments/abc123/too_many_applicants/"/>
    <published>2026-10-29T10:00:00+00:00</published>
    <title>Too many applicants, none of them real?</title>
  </entry>
</feed>"""


class Sources(unittest.TestCase):
    def test_reddit_feed(self):
        [d] = reddit.parse_feed(REDDIT_ATOM)
        self.assertEqual(d["author"], "tired_cto")
        self.assertIn("900 applicants", d["text"])
        self.assertNotIn("submitted by", d["text"])
        post = reddit._to_post(d, "startups")
        self.assertEqual(post.platform, "reddit")
        self.assertEqual(post.community, "startups")

    def test_hackernews_hit(self):
        p = hackernews.hit_to_post({"objectID": "42", "author": "pg", "title": "Ask HN: hiring",
                                    "story_text": "<p>Four months to hire</p>", "points": 120,
                                    "num_comments": 33, "created_at": "2026-10-29T10:00:00Z"}, "CTO at Example")
        self.assertEqual(p.url, "https://news.ycombinator.com/item?id=42")
        self.assertEqual(p.text, "Four months to hire")
        self.assertEqual(p.author.bio, "CTO at Example")

    def test_x_results(self):
        res = {"data": [{"id": "1", "text": "1200 applicants", "author_id": "u1", "created_at": "2026-10-28T16:49:00Z",
                         "public_metrics": {"like_count": 3700, "reply_count": 142, "impression_count": 135000}},
                        {"id": "2", "text": "low engagement", "author_id": "u1",
                         "public_metrics": {"like_count": 3}}],
               "includes": {"users": [{"id": "u1", "username": "expatanon", "name": "E", "description": "Founder"}]}}
        posts = x.results_to_posts(res, min_likes=50)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].url, "https://x.com/expatanon/status/1")
        self.assertEqual(posts[0].author.bio, "Founder")

    def test_x_needs_access_without_token(self):
        os.environ.pop("X_BEARER_TOKEN", None)
        posts, st = x.fetch(CFG)
        self.assertEqual((posts, st.state), ([], "needs_access"))

    def test_octolens_mapping_and_access(self):
        p = octolens.mention_to_post({"id": "m1", "url": "https://linkedin.com/posts/1", "body": "Hiring is broken",
                                      "source": "LinkedIn", "author": {"name": "Ana", "headline": "CTO at Acme"}})
        self.assertEqual((p.platform, p.author.bio), ("linkedin", "CTO at Acme"))
        os.environ.pop("OCTOLENS_API_KEY", None)
        self.assertEqual(octolens.fetch(CFG)[1].state, "needs_access")


class Scoring(unittest.TestCase):
    def sample(self):
        return [Post.from_dict(d) for d in json.loads((ROOT / "fixtures" / "sample_posts.json").read_text())]

    def test_keyword_scorer_and_digest(self):
        posts = [scorer.keyword_score(p) for p in self.sample()]
        tweet = posts[0]
        self.assertGreaterEqual(tweet.scores["fit"], 4)
        stances = {r.handle: r.stance for r in tweet.replies}
        self.assertEqual(stances["sample_cto_fintech"], "agrees")
        self.assertEqual(stances["sample_recruiter"], "neutral")
        md, rows = digest.build(posts, [], CFG, sample=True)
        self.assertIn("## Content", md)
        handles = {r["handle"] for r in rows}
        self.assertIn("sample_cto_fintech", handles)
        self.assertNotIn("sample_jobseeker", handles)
        self.assertNotIn("sample_recruiter", handles)

    def test_claude_scorer_parses_reply(self):
        reply = {"post": {"fit": 5, "author": 4, "reach": 5, "freshness": 5, "campaign": "senior-on-paper",
                          "risk": "none", "quote": "Most resumes are suspiciously well-tailored",
                          "seb_angle": "A. B.", "ad_hook": "1,200 applicants. Now what?"},
                 "people": [{"handle": "expatanon", "stance": "agrees", "role": "unknown", "company": "unknown",
                             "icp_fit": 2, "reason": "No bio"},
                            {"handle": "sample_cto_fintech", "stance": "agrees", "role": "CTO",
                             "company": "Series A fintech", "icp_fit": 5, "reason": "CTO hiring"}]}

        class FakeClient:
            messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
                content=[SimpleNamespace(type="text", text="```json\n" + json.dumps(reply) + "\n```")]))

        post = scorer.claude_score(self.sample()[0], CFG, FakeClient())
        self.assertEqual(post.scored_by, "claude")
        self.assertEqual(post.ad_hook, "1,200 applicants. Now what?")
        cto = next(r for r in post.replies if r.handle == "sample_cto_fintech")
        self.assertEqual((cto.icp_fit, cto.company), (5, "Series A fintech"))


if __name__ == "__main__":
    unittest.main()
