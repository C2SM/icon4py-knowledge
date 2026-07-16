---
name: weekly-slack-summary
description: "Load when generating the weekly Slack activity summary for the icon4py-knowledge repository."
---

# Weekly Slack summary for icon4py-knowledge

You are writing the weekly activity summary for the **icon4py-knowledge**
repository. This is a Quartz digital garden where design ideas and proposals for
icon4py are collected before they graduate to real work in the icon4py repo.

The summary will be posted to a Slack channel as one message. Write the final
message to the file path given in the user prompt (default:
`weekly_slack_summary.md`). Do not echo the full message in chat; just confirm
the file path and size.

## Time window

Cover the **last completed calendar week**: Monday 00:00 UTC to Sunday 23:59:59
UTC. Compute the bounds like this:

```bash
week_start=$(date -u -d 'monday - 1 week' +%Y-%m-%dT00:00:00Z)
week_end=$(date -u -d 'sunday - 1 week' +%Y-%m-%dT23:59:59Z)
```

Use these bounds for git history, GitHub searches, and any date-bounded
discovery.

## What to discover

Use the available tools to look around. Collect whatever feels relevant for the
last calendar week. Good starting points:

- Recent commits and merges: `git log --oneline --since="$week_start" --until="$week_end"`.
- GitHub issues and PRs opened, closed, or updated in that window. Use `gh`
  or `curl` with `$GITHUB_TOKEN`.
- New or updated proposals under `content/personal/` and `content/shared/`.
- Changes to `content/index.md` and new cross-links between notes.
- Frontmatter changes: status moves (draft -> reviewed -> final), new tags, new
  authors.
- Any obvious overlaps, conflicts, or stale drafts worth surfacing.

You do not need to enumerate every file. Curate: what would the team want to
know after a week away?

## Tone and format

- Keep it casual, brief, and useful. This is a Slack message, not a formal
  report.
- Do not use Markdown headings. Use `*bold*` for emphasis if you want (Slack
  mrkdwn).
- Format links as Slack mrkdwn: `<URL|label>`. Do not leave raw URLs.
- Use `-` bullets.
- Strongly aim for a single Slack message: under ~3,500 characters and ~40
  lines. Slack's practical limit is around 4,000 characters. If you are close,
  trim descriptions before dropping items.
- If the week was quiet, say so honestly. Then add one short nudge: revisit a
  dormant proposal, look for overlaps, move something from `personal/` toward
  `shared/`, or polish the index.

## Output

Write the final summary to the requested file. The file content is what gets
posted to Slack, so it should be ready to send.
