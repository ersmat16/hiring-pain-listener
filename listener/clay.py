"""Sends ICP fits to a Clay table through its webhook, so Clay can enrich them
(company size, funding, hiring activity) and feed the trigger account list.

Needs CLAY_WEBHOOK_URL: in Clay, create a table with a "Webhook" source and copy its URL.
"""
from __future__ import annotations

import os

from .http import post_json
from .models import SourceStatus


def send(rows: list[dict]) -> SourceStatus:
    url = os.environ.get("CLAY_WEBHOOK_URL", "")
    if not url:
        return SourceStatus("Clay (enrichment)", "needs_access", "Add CLAY_WEBHOOK_URL from a Clay webhook table.",
                            unlocks="Company size, funding and hiring activity for every ICP fit, straight into the trigger list.")
    sent = 0
    for r in rows:
        try:
            post_json(url, r)
            sent += 1
        except Exception:
            pass
    state = "ran" if sent == len(rows) else "failed"
    return SourceStatus("Clay (enrichment)", state, f"Sent {sent} of {len(rows)} people.", found=sent)
