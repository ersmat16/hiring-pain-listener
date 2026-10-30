"""Tiny HTTP helpers on the standard library, so the free sources need no extra packages."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

USER_AGENT = "hiring-pain-listener/0.1 (prototype; contact via repo)"


def get(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 20) -> bytes:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    return json.loads(get(url, params, headers))


def post_json(url: str, body: dict, headers: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}
