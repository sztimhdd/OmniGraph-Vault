# kb-v2.3 Web Research Supplement (orchestrator-gathered)

**Gathered:** 2026-07-02 via main-session MCP brave-search (MCP tools cannot run in sub-agents on this Databricks proxy — orchestrator ran these directly). Companion to kb-v2.3-RESEARCH.md (codebase-internal). Planner MUST read both.

## A. LLM markdown-cleaning prompt patterns (Stage 1 rewrite prompt)

Consensus from LLM-markdown-cleaning tooling (Crawl4AI `fit_markdown`, Apify AI-Web-to-Markdown, Crawlbase `md_readability`, evilmartians "clean markdown for LLMs"):

- **The task IS a solved shape**: "strip ads/nav/cookie-banners/boilerplate → emit clean semantic markdown, preserve headers/lists/code-blocks verbatim" is exactly what production markdown-cleaners do. Our rewrite prompt should frame the task in those terms.
- **Headers = chunk boundaries; keep them.** Lists stay lists, code blocks stay code blocks — the prompt must explicitly instruct "preserve structural elements, only remove noise."
- **Caveat from Crawl4AI docs:** "some sites have crucial data in footers/sidebars — verify textual quality." Maps to our success gate (length ≥20% of original) — guard against the LLM nuking real content it mistakes for boilerplate.
- **Markdown-structured prompts reduce hallucination** (neuralbuddies, arxiv 2411.10541): giving the LLM clearly-delimited input/output sections lowers the chance it invents content. → Rewrite prompt should use explicit delimiters around the dirty input and demand markdown-only output.

## B. Preserving image URLs verbatim (the critical risk)

- LLMs mangling/hallucinating URLs during rewrite is a KNOWN failure — mitigations that work:
  - **Explicit instruction + example**: "Image URLs of the form `http://localhost:8765/{hash}/{name}` and the `![...](...)` markdown around them MUST be reproduced BYTE-FOR-BYTE. Never alter, shorten, or invent a URL." Include a positive+negative few-shot pair.
  - **Post-hoc verification is the real safety net** (since there's no regex pre-pass): diff the set of `http://localhost:8765/` URLs in input vs output; if the sets differ, REJECT the rewrite for that article and fall back to keeping `body` (leave body_rewritten NULL). This makes the Task-1 validation gate enforceable and gives the backfill a per-article safety valve.
  - Prefer having the LLM emit the cleaned body while treating image lines as opaque tokens — do NOT ask it to "improve" or "describe" images.

## C. 2026 tech-blog reading-page design (Stage 2 refinement)

Consensus (UXPin 2026, Pimp My Type, USWDS, adoc-studio 2026 guide):

- **Measure: 50–75 chars (ideal ~66ch), NOT a fixed px.** Current 760px is in-range but a `max-width: 66ch` or `min(760px, 92vw)` is more robust across font-size changes. Keep ~760px measure (locked constraint) but consider `ch`-based expression.
- **Fluid type is standard**: `font-size: clamp(1rem, 0.9rem + 0.5vw, 1.25rem)` + `line-height ~1.5–1.6` for body. Directly supports the locked target (16px-fixed → clamp; mobile lh 1.8→1.6). Use `rem`, test at 200% zoom (WCAG 1.4.4).
- **Container queries** (2026): line length controllable at component level, not just viewport — optional upgrade for the article-body block.
- **line-height 1.8 is too loose for body** — appropriate only for captions/short text (USWDS "line-height 3" guidance). Confirms the 1.8→1.6 target.
- **Design-system references** to emulate (Stripe / Vercel / Linear): documented as the bar for the ui-ux-pro-max pass — restrained palette, strong type hierarchy, subtle code-block theming (vs dated Monokai), figure/caption structure.
- **ui-ux-pro-max skill** already carries 2026 style/palette/font-pairing intelligence — Stage 2 should drive design decisions through it rather than hand-picking values.

## D. Sources
- https://docs.crawl4ai.com/core/markdown-generation/ (fit_markdown, html2text options)
- https://apify.com/wiry_kingdom/ai-web-to-markdown (strip ads/nav/boilerplate task shape)
- https://evilmartians.com/chronicles/how-to-make-your-website-visible-to-llms (clean markdown at every URL)
- https://www.neuralbuddies.com/p/marking-up-the-prompt-how-markdown-formatting-influences-llm-responses (structure reduces hallucination)
- https://arxiv.org/html/2411.10541v1 (prompt formatting impact on LLM performance)
- https://www.uxpin.com/studio/blog/optimal-line-length-for-readability/ (50–75 char measure, clamp, WCAG 1.4.4)
- https://pimpmytype.com/line-length-line-height/ (measure 60–80 chars, line-height)
- https://designsystem.digital.gov/components/typography/ (line-height tokens; 1.8 = caption-only)
