---
confidence_level: high
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
- article:1272b434a5
- article:5a362bf61e
title: LangChain
---

# LangChain

## Definition / Overview

LangChain is an open-source software framework — and the company that develops it — for building applications powered by large language models (LLMs). It provides a modular set of abstractions for prompt management, tool calling, memory, retrieval, and workflow orchestration, allowing developers to chain together interoperable components and third-party integrations to build agents and LLM-powered applications. Beyond the core library, LangChain also publishes a broader ecosystem including LangGraph, `create_agent`, and Deep Agents, which sit at progressively higher levels of abstraction ^[article:5a362bf61e].

According to the LangChain GitHub repository, the project positions itself as "the agent engineering platform," emphasizing a standard interface for models, embeddings, and vector stores while remaining neutral across providers. The IBM "What Is LangChain?" reference describes the framework as a modular architecture in which components encapsulate the complex steps necessary to work with LLMs and can be chained together to build chatbots, RAG systems, and autonomous agents.

In the Chinese AI engineering community, LangChain is often discussed as a transitional framework — useful for quickly building skeletons but carrying real risks of technical debt for large enterprise systems ^[article:1272b434a5].

![AI Application Project Technical Architecture Selection Panorama](/static/img/dffd2cf86a/0.jpg)

## Architecture / Design

LangChain's architecture is layered. At its base sit primitive abstractions — `BaseMessage`, `ChatPromptTemplate`, model wrappers like `ChatAnthropic` and `ChatOpenAI`, output parsers, retrievers, and memory — composed via the LangChain Expression Language (LCEL), which uses pipe syntax (`prompt | llm | parser`) to express linear chains ^[article:5a362bf61e].

Above the primitives, the ecosystem exposes three layers of agent abstraction ^[article:5a362bf61e]:

- **LangGraph** — the lowest-level engine. Models workflows as a stateful directed graph of nodes, edges, and conditional routing, with explicit support for branching, loops, retries, human-in-the-loop interrupts, checkpointing, time travel, and persistence. Maximum control, more boilerplate.
- **`create_agent`** — a pre-built ReAct (Reason + Act) loop that runs on the LangGraph runtime. As of LangChain v1.0 it replaces the deprecated `AgentExecutor`, hiding graph wiring behind a simple `create_agent(model, tools=[...])` call.
- **Deep Agents** — the highest level of abstraction. Built on top of `create_agent`, it ships with a virtual file system, code sandbox, sub-agent orchestration, web/search, and cross-session long-term memory.

![Choosing the Right LangChain Tool: When to Use Each](/static/img/6b8c197d6a/0.jpg)

The ReAct loop inside `create_agent` follows a fixed cycle: User Input → Think → Choose Tool & Act → Observe Result → Think Again → (loop) → Final Answer ^[article:5a362bf61e].

![The ReAct Loop in create_agent](/static/img/6b8c197d6a/1.jpg)

Deep Agents wraps an Agent core with eight built-in capabilities — File System, Sandbox, Sub-agents, Tool Integrations, Long-term Memory, Web & Search, Memory, and the orchestrating Agent itself ^[article:5a362bf61e].

![Deep Agents: Built-in Capabilities](/static/img/6b8c197d6a/2.jpg)

In a typical enterprise deployment, the architecture path looks like: Client (Web/App/Mini Program) → Application Service (Based on LangChain) → LLM Service / Vector DB / external tools, with the LangChain layer integrating Prompt templates, Chain/Agent, tool integration, memory management, callback/logging, and custom business logic ^[article:1272b434a5].

## History / Origin

LangChain was created by Harrison Chase in late 2022 as an open-source Python library to glue together LLM calls, prompts, and tool use. It rapidly became a de facto standard for LLM-application prototyping, expanded to a TypeScript/JavaScript port (LangChain.js), and grew into a commercial company offering LangSmith (observability/evals), LangGraph (orchestration), and LangGraph Platform (hosting).

A key inflection occurred with **LangChain v1.0** (2025), in which the Agent abstraction was rebuilt on top of LangGraph — making LangGraph the execution engine for the entire ecosystem and deprecating the older `AgentExecutor` ^[article:5a362bf61e]. Harrison Chase has also become a prominent advocate for **context engineering**, the practice of dynamically curating an agent's context window, which LangChain's tooling is increasingly oriented around.

A notable benchmark moment: LangChain modified its Agent Harness architecture for Terminal Bench 2.0, demonstrating a 14% improvement in benchmark scores purely from harness optimization — and in a related experiment, ranking moved from outside the top 30 into the top 5 without changing the underlying model.

## Key Concepts / Components

- **Chain / LCEL** — Linear A → B → C composition via pipe syntax. Best for fixed sequences ^[article:5a362bf61e].
- **Agent (`create_agent`)** — Pre-built ReAct loop with native tool calling, structured output (Pydantic), middleware, and streaming ^[article:5a362bf61e].
- **LangGraph** — Stateful graph runtime with nodes, edges, conditional routing, `StateGraph`, `MessagesState`, `interrupt`, `checkpointer` (e.g. `InMemorySaver`/`MemorySaver`), `thread_id`-based persistence, and time travel ^[article:5a362bf61e].
- **Deep Agents** — High-level agents with filesystem, sandbox, sub-agents, and long-term memory ^[article:5a362bf61e].
- **Prompt Template / `ChatPromptTemplate`** — Structured prompt construction.
- **Memory Management** — Short-term conversation state plus optional long-term retrieval-backed memory.
- **Tool Integration** — Native function/tool calling against OpenAI, Anthropic, Google, etc.; integrations with vector stores like Pinecone and Chroma.
- **Callback / Logging** — Hooks for observability, frequently routed into LangSmith.
- **Context Engineering** — The methodology — championed by Harrison Chase — of selecting, compressing, and timing what enters the model's context window.

## Notable Use Cases / Examples

**When LangChain (the linear chain layer) fits well** — RAG, summarization, simple Q&A, fixed-sequence workflows, rapid prototypes ^[article:5a362bf61e]. The `create_agent` loop is well suited to basic chatbots, tool-using agents, customer support bots, and structured-output APIs.

**When LangGraph fits better** — Workflows requiring retries, loops, human approval, state persistence across sessions, multi-agent coordination, or custom branching ^[article:5a362bf61e]. A canonical example is BugLens's code-review pipeline, where the analysis agent occasionally needs to re-fetch context — a conditional back-edge that is awkward in pure LangChain but natural as a `should_loop` conditional edge in LangGraph.

**When Deep Agents fits** — Coding assistants (filesystem + sandbox), research assistants (memory + sub-agents), and multi-step autonomous tasks (planning + sub-agent orchestration) ^[article:5a362bf61e].

**When NOT to use LangChain — the 叶小钗 critique** — Based on real B2B AI delivery experience, the article *为什么我们不用LangChain？* argues for a project-size-driven decision ^[article:1272b434a5]:

- **Small projects / Demos** — Use native API calls (or low-code platforms like Coze/Dify). Frameworks add unnecessary abstraction.
- **Medium / time-pressured projects** — LangChain is acceptable as a transitional skeleton, but teams must guard against technical debt, plan refactoring, and isolate LangChain calls behind an adapter pattern.
- **Large / enterprise projects** — Self-build is strongly recommended. LangChain's Python-only ecosystem clashes with Java enterprise stacks (Spring Cloud, Dubbo); cross-language bridging via RPC/HTTP introduces latency and format risks; built-in logs/monitoring don't align with corporate observability stacks; and most teams lack the framework-maintenance capacity to absorb breaking upgrades ^[article:1272b434a5]. Spring AI is presented as a more cost-effective alternative for Java shops.

The framework comparison table from that article rates LangChain at 2-star flexibility, medium/high onboarding, high operational complexity (black-box debugging), and difficult microservices adaptation — versus 5-star flexibility for native development and 4-star for self-built frameworks ^[article:1272b434a5].

![AI Development Framework Comparison](/static/img/dffd2cf86a/2.jpg)

The accompanying decision guide maps project size to the recommended approach — Native for demos, LangChain (with technical-debt warning ⚠) for medium/transitional projects, Self-Dev (🚀) for enterprise scale ^[article:1272b434a5].

![AI Application Development Framework Selection Decision Guide](/static/img/dffd2cf86a/1.jpg)

A complementary decision UI poses concrete questions — "Does my workflow follow a fixed sequence with no loops?" → LangChain; "Do I need agents to retry or loop based on output quality?" → LangGraph; "Is state persistence across sessions required?" → LangGraph; "Am I doing RAG, summarization, or simple Q&A?" → LangChain ^[article:5a362bf61e].

A practical "quick reference" matches situation to tool: basic chatbot/tool-user/support bot/structured output → `create_agent`; coding assistant / research assistant / multi-step autonomous task → Deep Agents; custom workflows / branching / human-in-the-loop / durability → LangGraph ^[article:5a362bf61e].

![Quick Reference: Choosing the Right Tool](/static/img/6b8c197d6a/3.jpg)

## Cross-references

- [[langgraph]]
- [[create-agent]]
- [[deep-agents]]
- [[harrison-chase]]
- [[context-engineering]]
- [[react-architecture]]
- [[langsmith]]
- [[agent-harness]]
- [[harness-engineering]]
- [[ai-agent]]
- [[spring-ai]]
- [[mcp]]
- [[lcel]]
- [[buglens]]

## Further Reading

- [GitHub — langchain-ai/langchain](https://github.com/langchain-ai/langchain) — Official repository; describes LangChain as "the agent engineering platform" and points to Deep Agents and LangGraph.
- [Open Source AI Agent Framework | Build Agents Faster — LangChain](https://www.langchain.com/langchain) — Official product page covering `create_agent`, the ReAct pattern on LangGraph's durable runtime, and 1000+ integrations.
- [LangGraph: Agent Orchestration Framework for Reliable AI Agents](https://www.langchain.com/langgraph) — Official LangGraph page with FAQ and customer testimonials.
- [LangChain: Observe, Evaluate, and Deploy Reliable AI Agents](https://www.langchain.com/) — Overview of the LangSmith agent engineering platform (observability, evaluation, deployment, Fleet).
- [Choosing the Right Multi-Agent Architecture — LangChain Blog](https://www.langchain.com/blog/choosing-the-right-multi-agent-architecture) — Patterns for supervisor/sub-agent architectures and skill-based specializations.
- [What Is LangChain? — IBM](https://www.ibm.com/think/topics/langchain) — Vendor-neutral explainer covering ChatWatsonx, `bind_tools`, and LangGraph's graph-based architecture.
- [AI Agent Frameworks: Choosing the Right Foundation — IBM](https://www.ibm.com/think/insights/top-ai-agent-frameworks) — Compares LangChain to CrewAI, AutoGen, BeeAI, and others.
- [Understanding LangChain Agent Framework — Analytics Vidhya](https://www.analyticsvidhya.com/blog/2024/07/langchains-agent-framework/) — Hands-on tutorial building an OpenAI-Functions agent with the Tavily search tool.
- [LangChain 还是 LangGraph？一个是编排一个是工具包 — DeepHub IMBA](http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247516561&idx=1&sn=ffe0c0f0bb00090238aad378ecaec99a&chksm=feb4cf30c9c34626597d1d27857892545bb0af830b1d8fc38afd3dad8fce50a4e529d6501bbc#rd) — Side-by-side LangChain vs. LangGraph implementation of a 3-stage code-review pipeline.
- [2026年的 ReAct Agent架构解析：原生 Tool Calling 与 LangGraph 状态机 — DeepHub IMBA](http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247516571&idx=1&sn=0fcb67313c194c10276f4f2628c2fbf5&chksm=feb4cf3ac9c3462c40dc765792f4b8e2943e4f52f6d88750b6a60902f00e3616cbd94be58767#rd) — Modern ReAct with native tool calling, replacing fragile string-parsing prompts.
- [LangChain 生态里的三层抽象:LangGraph、create_agent、Deep Agents — DeepHub IMBA](http://mp.weixin.qq.com/s?__biz=MzU5OTM2NjYwNg==&mid=2247516601&idx=1&sn=c467e0dc5c0f1ff65fe5ff7ffd9b4ca2&chksm=feb4cf18c9c3460ee6c961e568a29a0cdc7097132ffd2781ceb10a99881a45814d172423864c#rd) — Detailed walkthrough of the three abstraction layers by Ramakrishna Gedala.