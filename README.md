# Hiring pain listener

An agent for Cloud Employee that finds founders and CTOs talking about the pain of hiring engineers, and turns those conversations into two lists every day:

- **Content:** posts worth reacting to in Seb's posts and paid LinkedIn campaigns, each with a draft angle, an ad hook and the key quote.
- **People:** the poster and anyone in the replies who agrees and fits the ICP, ready for the SDR and the Clay trigger list.

It drafts and flags. A person approves. Nothing posts or sends on its own.

Built by Matthew Erskine as a working prototype. **[See a real run →](examples/digest.md)**

## What works today, and what needs access

| Source | Status | Cost | What it adds |
| --- | --- | --- | --- |
| Reddit | Works now, no key | Free | Honest, detailed pain. Mostly anonymous, so best for content |
| Hacker News | Works now, no key | Free | Founders and CTOs; profiles often name their company |
| X | Add `X_BEARER_TOKEN` | Pay per use, roughly $100 to $200 a month at this volume | Real names, bios and replies |
| LinkedIn, podcasts, newsletters, reviews | Add `OCTOLENS_API_KEY` | Octolens subscription, about $120 to $160 a month | Names, titles and companies; podcast guests; unhappy competitor clients |
| Claude scoring | Add `ANTHROPIC_API_KEY` | Pay per use, pennies per post | Judgement on fit, ICP and risk, plus the drafted angles |
| Clay enrichment | Add `CLAY_WEBHOOK_URL` | Clay credits | Company size, funding and hiring activity for each ICP fit |
| Slack digest | Add `SLACK_WEBHOOK_URL` | Free | Posts the top 3 content posts, ICP names and source status to a Slack channel after each run |

Without a key, a source is skipped and the digest says what adding it would unlock. Without `ANTHROPIC_API_KEY`, a basic keyword scorer runs instead so the pipeline still works end to end.

Prices are estimates from October 2026. Check each provider before committing.

## How it works

1. **Listen.** Searches each source for the keywords in `config.yaml` over the lookback window set in `config.yaml`.
2. **Narrow down.** A cheap keyword pass keeps the 40 most promising posts, so Claude costs stay predictable.
3. **Read the replies.** Pulls the replies under each post (Reddit, Hacker News and X).
4. **Score.** Claude rates each post on fit, author, reach and freshness, tags the campaign it supports, flags risks, and drafts the Seb angle and ad hook. It then checks every person in the conversation: do they agree, what is their role and company, and how well do they fit the ICP.
5. **Hand over.** Writes the digest, a CSV of ICP fits for the SDR, and sends those people to Clay.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # add whichever keys you have; all are optional

python -m listener.run --sample   # demo on saved example posts, no network needed
python -m listener.run            # live run on every source you have access to
python -m unittest -v             # offline tests
```

Output lands in `output/`:

- `digest-YYYY-MM-DD.md`: the daily digest, with Content, People and a source status table.
- `people-YYYY-MM-DD.csv`: ICP fits for the SDR.
- `posts-YYYY-MM-DD.json`: everything scored, for debugging.

## Run it every day

`.github/workflows/daily.yml` runs the listener every weekday morning on GitHub Actions and saves the digest as a downloadable artifact. Add your keys as repository secrets with the same names as in `.env.example`.

## Change what it looks for

Everything is in `config.yaml`: keywords, subreddits, the ICP definition, the campaigns posts are tagged with, and the score thresholds. No code changes needed.

## Guardrails

- **Paid ads never quote a named person** without their permission. Use the stat or a paraphrase.
- **Never quote job seekers in distress**, even anonymously.
- **Posts that criticise engineers by country** are flagged as a risk, because they clash with Cloud Employee's model.
- **Follow-ups never mention someone's post.** They offer something useful that matches what the person said.

## Notes for whoever builds it out

- `listener/sources/octolens.py` maps Octolens fields with a best guess. Confirm the names against Octolens's API docs during the free trial and adjust `FIELD_MAP`. Also check whether Octolens returns replies under a post. If it doesn't, LinkedIn commenters need Clay or PhantomBuster.
- Reddit's RSS feeds are free, but check Reddit's terms before commercial use.
- `fixtures/sample_posts.json` mixes real public posts with replies marked SAMPLE, which are invented test data, not real people.
