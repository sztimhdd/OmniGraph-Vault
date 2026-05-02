"""Estimate monthly cost for batch ingestion with Vertex AI + SiliconFlow + DeepSeek.

Standalone: no network calls, no imports of project modules. Rates hardcoded at top.
Rerun after editing rates if GCP / DeepSeek / SiliconFlow pricing changes.

Usage:
    python scripts/estimate_vertex_ai_cost.py --articles 282 --avg-images-per-article 25

Output format is pinned verbatim to MILESTONE_v3.2_REQUIREMENTS.md §B5.4. All ¥ values
are ESTIMATES for budget planning, not invoices.
"""
from __future__ import annotations

import argparse

# ---------------------------------------------------------------------------
# Pricing constants (2026-04 published rates). Edit and re-run if rates change.
# ---------------------------------------------------------------------------

# Vertex AI embedding (gemini-embedding-004): $0.00002 per 1k characters
VERTEX_EMBEDDING_PER_1K_CHARS_USD: float = 0.00002

# SiliconFlow Qwen3-VL-32B: ¥0.0013 per image
SILICONFLOW_PER_IMAGE_CNY: float = 0.0013

# DeepSeek chat pricing (CNY per 1k tokens)
DEEPSEEK_INPUT_PER_1K_TOKENS_CNY: float = 0.0014
DEEPSEEK_OUTPUT_PER_1K_TOKENS_CNY: float = 0.0028

# USD → CNY conversion rate (update manually on material FX moves)
USD_TO_CNY: float = 7.2

# ---------------------------------------------------------------------------
# Workload assumptions (observed averages from v3.1 batches)
# ---------------------------------------------------------------------------

AVG_CHARS_PER_CHUNK: int = 1500
AVG_CHUNKS_PER_ARTICLE: int = 30
AVG_INPUT_TOKENS_PER_CLASSIFICATION: int = 4000
AVG_OUTPUT_TOKENS_PER_CLASSIFICATION: int = 800


def estimate_embedding_cost_cny(articles: int) -> float:
    """Vertex AI embedding cost in CNY for N articles (30 chunks x 1500 chars/chunk)."""
    total_chars = articles * AVG_CHUNKS_PER_ARTICLE * AVG_CHARS_PER_CHUNK
    cost_usd = (total_chars / 1000.0) * VERTEX_EMBEDDING_PER_1K_CHARS_USD
    return cost_usd * USD_TO_CNY


def estimate_vision_cost_cny(articles: int, images_per_article: int) -> float:
    """SiliconFlow vision cost in CNY for N articles with M images each."""
    return articles * images_per_article * SILICONFLOW_PER_IMAGE_CNY


def estimate_llm_cost_cny(articles: int) -> float:
    """DeepSeek LLM cost in CNY for classification + chunk extraction per article."""
    input_cost = (AVG_INPUT_TOKENS_PER_CLASSIFICATION / 1000.0) * DEEPSEEK_INPUT_PER_1K_TOKENS_CNY
    output_cost = (AVG_OUTPUT_TOKENS_PER_CLASSIFICATION / 1000.0) * DEEPSEEK_OUTPUT_PER_1K_TOKENS_CNY
    return articles * (input_cost + output_cost)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate monthly ingestion cost with Vertex AI + SiliconFlow + DeepSeek."
    )
    parser.add_argument("--articles", type=int, required=True, help="Number of articles per month")
    parser.add_argument(
        "--avg-images-per-article",
        type=int,
        required=True,
        help="Average number of images per article",
    )
    args = parser.parse_args()

    embedding = estimate_embedding_cost_cny(args.articles)
    vision = estimate_vision_cost_cny(args.articles, args.avg_images_per_article)
    llm = estimate_llm_cost_cny(args.articles)
    total = embedding + vision + llm

    # Output format MUST match PRD §B5.4 verbatim.
    print(
        f"Estimated cost for {args.articles} articles with {args.avg_images_per_article} images/article:"
    )
    print(f"- Embedding (Vertex AI): ¥{embedding:.2f}/month (vs ¥0 free tier)")
    print(f"- Vision (SiliconFlow): ¥{vision:.2f}/month")
    print(f"- LLM (DeepSeek): ¥{llm:.2f}/month")
    print(f"- Total: ¥{total:.2f}/month")


if __name__ == "__main__":
    main()
