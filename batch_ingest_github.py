"""
Batch ingest 50 curated AI-tool GitHub repos into LightRAG.
Resumable: repos already in entity_registry.json are skipped automatically.
Run: venv/Scripts/python batch_ingest_github.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPOS = [
    # Agent frameworks
    "https://github.com/langchain-ai/langchain",
    "https://github.com/run-llama/llama_index",
    "https://github.com/microsoft/autogen",
    "https://github.com/crewAIInc/crewAI",
    "https://github.com/pydantic/pydantic-ai",
    "https://github.com/griptape-ai/griptape",
    "https://github.com/letta-ai/letta",
    "https://github.com/All-Hands-AI/OpenHands",
    # LLM orchestration / routing
    "https://github.com/BerriAI/litellm",
    "https://github.com/ollama/ollama",
    "https://github.com/vllm-project/vllm",
    "https://github.com/ggerganov/llama.cpp",
    "https://github.com/huggingface/transformers",
    # RAG / Knowledge graph
    "https://github.com/HKUDS/LightRAG",
    "https://github.com/microsoft/graphrag",
    "https://github.com/chroma-core/chroma",
    "https://github.com/qdrant/qdrant",
    "https://github.com/weaviate/weaviate",
    "https://github.com/lancedb/lancedb",
    "https://github.com/milvus-io/milvus",
    # MCP / tool use
    "https://github.com/modelcontextprotocol/python-sdk",
    "https://github.com/modelcontextprotocol/servers",
    "https://github.com/anthropics/anthropic-sdk-python",
    # Memory systems
    "https://github.com/topoteretes/cognee",
    "https://github.com/mem0ai/mem0",
    "https://github.com/getzep/graphiti",
    # Eval / observability
    "https://github.com/explodinggradients/ragas",
    "https://github.com/confident-ai/deepeval",
    "https://github.com/langfuse/langfuse",
    "https://github.com/Arize-ai/phoenix",
    "https://github.com/wandb/weave",
    # AI coding assistants
    "https://github.com/aider-chat/aider",
    "https://github.com/continuedev/continue",
    "https://github.com/cline/cline",
    "https://github.com/safishamsi/graphify",
    # Chinese LLM ecosystem
    "https://github.com/QwenLM/Qwen-Agent",
    "https://github.com/QwenLM/Qwen2.5",
    "https://github.com/InternLM/InternLM",
    "https://github.com/THUDM/ChatGLM3",
    "https://github.com/baichuan-inc/Baichuan2",
    "https://github.com/hiyouga/LLaMA-Factory",
    # Workflow / automation
    "https://github.com/n8n-io/n8n",
    "https://github.com/prefecthq/prefect",
    # Structured output / tooling
    "https://github.com/instructor-ai/instructor",
    "https://github.com/outlines-dev/outlines",
    "https://github.com/jxnl/instructor",
    # Prompt engineering / optimization
    "https://github.com/dspy-ai/dspy",
    "https://github.com/stanfordnlp/dspy",
    # Security / guardrails
    "https://github.com/guardrails-ai/guardrails",
    "https://github.com/NVIDIA/NeMo-Guardrails",
]

REGISTRY_FILE = Path(__file__).parent / "entity_registry.json"
LOG_FILE = Path(__file__).parent / "batch_ingest_github.log"


def load_registry() -> set:
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, encoding="utf-8") as f:
            return set(json.load(f).keys())
    return set()


def log(msg: str):
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    already_ingested = load_registry()
    to_ingest = [r for r in REPOS if r not in already_ingested]
    # Deduplicate (some repos listed twice)
    seen = set()
    to_ingest = [r for r in to_ingest if not (r in seen or seen.add(r))]

    log(f"=== batch_ingest_github.py start ===")
    log(f"Total repos: {len(REPOS)} | Already ingested: {len(already_ingested)} | To ingest: {len(to_ingest)}")

    succeeded, failed = 0, []

    for i, url in enumerate(to_ingest, 1):
        log(f"\n[{i}/{len(to_ingest)}] {url}")
        result = subprocess.run(
            [sys.executable, "ingest_github.py", url],
            capture_output=True, text=True, encoding="utf-8",
            cwd=Path(__file__).parent,
        )
        if result.returncode == 0:
            succeeded += 1
            log(f"  OK")
        else:
            failed.append(url)
            log(f"  FAILED: {result.stderr.strip()[-200:]}")
        # Respect rate limits
        time.sleep(5)

    log(f"\n=== DONE: {succeeded} succeeded, {len(failed)} failed ===")
    if failed:
        log("Failed repos:")
        for r in failed:
            log(f"  {r}")


if __name__ == "__main__":
    main()
