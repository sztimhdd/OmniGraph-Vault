"""
MVP batch ingestion for curated Hermes/OpenClaw KOL articles.

Rate-limited: 90s sleep between articles to respect Gemini RPM (15 RPM Flash)
and WeChat anti-scraping. Each article triggers ~3-5 Gemini calls via ingest_wechat.py.

Usage:
    python batch_ingest_kol_mvp.py [--dry-run]

Total runtime: ~12 minutes for 8 articles.
"""
import subprocess
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
INGEST_SCRIPT = PROJECT_ROOT / "ingest_wechat.py"

SLEEP_BETWEEN_ARTICLES = 60
INGEST_TIMEOUT = 600

ARTICLES: list[tuple[str, str, str]] = [
    (
        "叶小钗",
        "Harness 到底是什么？看看 OpenClaw、Hermes、Claude Code 的演绎吧",
        "http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500767&idx=1&sn=b3d620a57e8833c4928da40f67fdecd1&chksm=ce76a5dbf9012ccdd1b4702fc96b85fe496591549c109333872f89d16b133323ade3b9e07a94#rd",
    ),
    (
        "叶小钗",
        "【万字】OpenClaw vs Hermes：一文深入拆解两大 Agent 框架",
        "http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500597&idx=1&sn=d601f66ac0d8d9749fa42a4d01fdd060&chksm=ce76a531f9012c27ec9dc29fba6ee30faf8f0a8e7b445761c404465307c5ffb38c9b6cc4f38a#rd",
    ),
    (
        "叶小钗",
        "Claude 工程师亲授 OpenClaw 调教指南：Skills 的工程化心法",
        "http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247500013&idx=1&sn=db9d9c4120b846f1783132b2e87671ce&chksm=ce76a6e9f9012fff35da20503aa845225e41be4cfcf65d402991c692a8009e67bf9796ec1b53#rd",
    ),
    (
        "叶小钗",
        "【万字】OpenClaw 上下文工程/记忆系统 全解析",
        "http://mp.weixin.qq.com/s?__biz=Mzg2MzcyODQ5MQ==&mid=2247499867&idx=1&sn=beae552f3459775b39f24002fb282fe7&chksm=ce76a65ff9012f497475cbd3dcbbae51e299e2d45dc21f010927141c99163ecd0abcc6ef3407#rd",
    ),
    (
        "智猩猩",
        "聊聊OpenClaw的AgentLoop",
        "http://mp.weixin.qq.com/s?__biz=MjM5ODExNDA2MA==&mid=2450001665&idx=1&sn=428ea4bc92a80db944a9f2e034da31f3&chksm=b13309628644807455b72a8e75958a0e2152bb40afc8d802ed6bf7bed73b0a67e71af3869def#rd",
    ),
    (
        "海滨code",
        "Hermes Agent 一周暴涨五万 Star，但我劝你别急着追",
        "http://mp.weixin.qq.com/s?__biz=MzYzODc4ODc2NQ==&mid=2247483748&idx=1&sn=ff3bb3329a2777f3c2cb84502dc6dd69&chksm=f0dd3496c7aabd80271164eaa5ae854e7ac4ad3a6959f5ec3a5046d30386e749327fb3db7c81#rd",
    ),
    (
        "老顾聊技术",
        "OpenClaw---小龙虾的原理分析，这一篇就够了",
        "http://mp.weixin.qq.com/s?__biz=MzU3NDg3MzUwMw==&mid=2247487001&idx=1&sn=43d6202e1eae5889896e4c80754862fc&chksm=fd2a84e9ca5d0dffdc21667de9add878b3f328c1f8c8a80288d2c8e7c2725427012d0b050699#rd",
    ),
    (
        "阿里通义实验室",
        "可复用的Skill封装实践：当OpenClaw接入通义晓蜜外呼",
        "http://mp.weixin.qq.com/s?__biz=MzkxMTYyMTAzNA==&mid=2247499613&idx=1&sn=cffbdc450e8ba0005545e27ae636c9e4&chksm=c11bd198f66c588efe11d4cbfb9814d7642b298dfcc393dceda409bfefb5cd2759a10ec85e7b#rd",
    ),
]


def get_python() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def ingest_one(url: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    try:
        result = subprocess.run(
            [get_python(), str(INGEST_SCRIPT), url],
            capture_output=False,
            timeout=INGEST_TIMEOUT,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Timeout after %ds — skipping: %s", INGEST_TIMEOUT, url)
        return False


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    python_exe = get_python()

    logger.info("Python: %s", python_exe)
    logger.info("Articles: %d | Sleep: %ds | Dry run: %s", len(ARTICLES), SLEEP_BETWEEN_ARTICLES, dry_run)
    logger.info("Estimated runtime: ~%d minutes", len(ARTICLES) * SLEEP_BETWEEN_ARTICLES // 60)

    results: list[dict] = []
    for i, (author, title, url) in enumerate(ARTICLES, 1):
        logger.info("[%d/%d] %s — %s", i, len(ARTICLES), author, title)
        success = ingest_one(url, dry_run)
        status = "dry_run" if dry_run else ("ok" if success else "FAILED")
        results.append({"author": author, "title": title, "status": status})
        logger.info("  → %s", status)

        if i < len(ARTICLES) and not dry_run:
            logger.info("  Sleeping %ds (rate limit)...", SLEEP_BETWEEN_ARTICLES)
            time.sleep(SLEEP_BETWEEN_ARTICLES)

    ok = sum(1 for r in results if r["status"] in ("ok", "dry_run"))
    fail = sum(1 for r in results if r["status"] == "FAILED")
    logger.info("=== DONE: %d ok, %d failed ===", ok, fail)

    for r in results:
        marker = "✓" if r["status"] != "FAILED" else "✗"
        logger.info("  %s %s — %s", marker, r["author"], r["title"])


if __name__ == "__main__":
    main()
