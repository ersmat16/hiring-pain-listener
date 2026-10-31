"""The two things the agent passes around: posts and the people in them."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Person:
    platform: str
    handle: str
    name: str = ""
    bio: str = ""            # profile text: the main clue for ICP fit
    profile_url: str = ""
    said: str = ""           # what they wrote in this conversation
    is_author: bool = False
    # filled in by the scorer
    stance: str = ""         # agrees | neutral | disagrees
    role: str = ""
    company: str = ""
    icp_fit: int = 0
    reason: str = ""


@dataclass
class Post:
    platform: str
    id: str
    url: str
    text: str
    author: Person
    created_at: str = ""     # ISO 8601
    title: str = ""
    community: str = ""      # subreddit, HN, or empty
    likes: int = 0
    replies_count: int = 0
    views: int = 0
    replies: list[Person] = field(default_factory=list)
    # filled in by the scorer
    scores: dict = field(default_factory=dict)   # fit, author, reach, freshness
    campaign: str = ""
    risk: str = ""
    quote: str = ""
    seb_angle: str = ""
    ad_hook: str = ""
    use: str = ""            # "act" | "content" | "skip"
    use_why: str = ""
    scored_by: str = ""      # "claude" or "keywords"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Post":
        d = dict(d)
        d["author"] = Person(**d["author"])
        d["replies"] = [Person(**r) for r in d.get("replies", [])]
        return Post(**d)


@dataclass
class SourceStatus:
    name: str
    state: str               # ran | needs_access | failed | disabled
    detail: str = ""
    found: int = 0
    unlocks: Optional[str] = None
