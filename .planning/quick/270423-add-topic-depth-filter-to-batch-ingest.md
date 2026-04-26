# Add Topic + Depth Filtering to batch_ingest_from_spider.py

## Background

Currently `batch_ingest_from_spider.py` scans all KOL articles and ingests **everything** — no filtering. This wastes Apify credits + Gemini Vision API calls on shallow news blurbs, irrelevant topics, and low-value articles like "Harness 到底是什么？看看 OpenClaw、Hermes、Claude Code 的演绎吧".

We need a **Pass 2: Filter** step between scanning and ingesting, using a single cheap LLM batch call (DeepSeek V3, ~$0.0003/call) to classify and filter.

## Requirements

### CLI Arguments (add to argparse)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--topic-filter` | str | None | Required topic to include (e.g. "AI agents", "LLM inference"). When set, only articles relevant to this topic pass. |
| `--exclude-topics` | str | None | Comma-separated topics/subjects to exclude (e.g. "OpenClaw", "Harness"). Articles primarily about these topics are skipped. |
| `--min-depth` | int | 2 | Minimum depth score 1-3. 1=news blurb/announcement, 2=tutorial/guide/comparison, 3=deep technical analysis. Default 2 (skip shallow news). |

### Filtering Logic

1. **Batch all article titles** from the scan step into a single LLM call
2. **DeepSeek API** (`https://api.deepseek.com/v1/chat/completions`, model `deepseek-chat`) classifies each article with:
   - `depth_score`: 1-3 integer
   - `relevant`: true/false (is it about --topic-filter?)
   - `excluded`: true/false (is it primarily about any --exclude-topics?)
   - `reason`: short explanation
3. Only articles that pass **all** criteria proceed to ingestion:
   - `depth_score >= min_depth`
   - `relevant == true` (if --topic-filter is set)
   - `excluded == false` (if --exclude-topics is set)

### Output

After scanning but before ingesting, print a summary table like:

```
=== Filter Results ===
Pass: 12 articles
Filtered out:
  3 - depth too low (news blurb)
  2 - off-topic (not about AI agents)
  1 - excluded topic (OpenClaw)
  ---
  6 total skipped
```

### Implementation Notes

- **DeepSeek API Key**: read from env var `DEEPSEEK_API_KEY` or `config.DEEPSEEK_API_KEY` if available. Also check `~/.hermes/config.yaml` or just accept as env var.
- **Batch size**: DeepSeek V3 has 64K context. If >200 articles, split into batches of 200.
- **Rate limiting**: DeepSeek V3 is generous (~500 RPM). No special delay needed.
- **Error handling**: If the API call fails, log a warning and **pass through** all articles (fail open — don't block ingestion on filter failure).
- **Dry-run mode**: The existing `--dry-run` already skips ingestion. The filter step should still run and show results even in dry-run, so the user can preview what would be ingested.

### Expected Behavior

Without `--topic-filter` and `--exclude-topics` flags, behavior is **unchanged** (all articles pass through). This preserves backward compatibility.

Example usage:
```bash
# Filter for AI-related deep dives, exclude OpenClaw
python batch_ingest_from_spider.py --topic-filter "AI" --exclude-topics "OpenClaw,Harness" --days-back 30 --max-articles 20

# Dry-run to preview what would be ingested
python batch_ingest_from_spider.py --topic-filter "AI agents" --dry-run --days-back 90

# Original behavior (no filtering)
python batch_ingest_from_spider.py --days-back 30 --max-articles 50
```
