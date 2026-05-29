---
title: Copilot Studio
created: 2026-05-29
last_updated: 2026-05-29
sources:
  - id: 1
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/fundamentals-what-is-copilot-studio
    title: Microsoft Learn — What is Copilot Studio
  - id: 2
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-create-edit-topics
    title: Microsoft Learn — Topics in Copilot Studio
  - id: 3
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp
    title: Microsoft Learn — Extend agents with MCP actions
  - id: 4
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/knowledge-copilot-studio
    title: Microsoft Learn — Knowledge sources
  - id: 5
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/autonomous-agents
    title: Microsoft Learn — Autonomous agents guidance
  - id: 6
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/generative-orchestration
    title: Microsoft Learn — Generative orchestration guidance
  - id: 7
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/billing-licensing
    title: Microsoft Learn — Copilot Studio billing and licensing
  - id: 8
    type: web
    ref: https://www.microsoft.com/en-us/microsoft-365-copilot/pricing/copilot-studio
    title: Microsoft 365 Copilot Studio pricing page
  - id: 9
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/geo-data-residency
    title: Microsoft Learn — Geo data residency
  - id: 10
    type: web
    ref: https://learn.microsoft.com/en-us/power-platform/admin/geographical-availability-copilot
    title: Microsoft Learn — Geographical availability of Copilot
  - id: 11
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/admin-data-loss-prevention
    title: Microsoft Learn — Data Loss Prevention for Copilot Studio
  - id: 12
    type: web
    ref: https://learn.microsoft.com/en-us/purview/ai-copilot-studio
    title: Microsoft Learn — Purview AI activities for Copilot Studio
  - id: 13
    type: web
    ref: https://github.com/microsoft/skills-for-copilot-studio
    title: GitHub — microsoft/skills-for-copilot-studio
  - id: 14
    type: web
    ref: https://learn.microsoft.com/en-us/power-platform/developer/cli/reference/copilot
    title: Microsoft Learn — pac copilot CLI reference
  - id: 15
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-test-bot
    title: Microsoft Learn — Test pane
  - id: 16
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-agent-evaluation-create
    title: Microsoft Learn — Agent Evaluation
  - id: 17
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/generative-mode-guidance
    title: Microsoft Learn — Generative mode guidance
  - id: 18
    type: web
    ref: https://learn.microsoft.com/en-us/answers/questions/5645109/text-extraction-from-file-in-copilot-studio-how
    title: Microsoft Q&A — PDF text extraction in Copilot Studio
  - id: 19
    type: web
    ref: https://learn.microsoft.com/en-us/answers/questions/5620653/copilot-studio-generative-nodes-jumping-between-to
    title: Microsoft Q&A — Generative nodes jumping between topics
  - id: 20
    type: builtin
    title: Microsoft public documentation synthesis (Copilot Studio research, 2026-05-29)
  - id: 21
    type: builtin
    title: Reddit r/copilotstudio community reports (low-confidence pattern observations)
confidence_level: high
---

# Copilot Studio

## Definition / Overview

**Microsoft Copilot Studio** is a low-code platform for building, deploying, and governing custom AI agents inside the Microsoft cloud[^1][^20]. It is the successor to Power Virtual Agents and sits inside the Power Platform alongside Power Apps and Power Automate, sharing the same environment, solution, and Dataverse infrastructure[^1][^14]. Authors compose agents from a small set of primitives — topics, knowledge sources, actions, triggers, variables, and channels — using either the web maker portal at `copilotstudio.microsoft.com`, the Teams-embedded maker app, or YAML manifests edited in code editors such as VS Code or Claude Code via the first-party `microsoft/skills-for-copilot-studio` plugin[^1][^13].

A Copilot Studio agent runs on the **Copilot Studio runtime** and can publish to many channels: Microsoft Teams, the Microsoft 365 Copilot chat surface (BizChat), SharePoint, Power Pages, an embedded web app via the Direct Line API, telephony via Azure Communication Services, and others[^20]. This distinguishes it from a [[declarative-agent]], which is a JSON-manifest extension of Microsoft 365 Copilot and runs on Microsoft's first-party Sydney orchestrator instead of the Copilot Studio runtime[^20]. Copilot Studio supports custom orchestration logic, deterministic Power Fx expressions, Power Automate cloud flows, AI Builder prompts, custom connectors, MCP tools, and Azure Functions, while declarative agents have no place to host such logic[^3][^20].

The platform is positioned as the path of least friction to a production-quality agent inside the Microsoft 365 estate when the agent needs both LLM-grounded conversation and deterministic business logic[^20].

## Architecture / Design

A Copilot Studio agent is composed of seven primitives[^1][^2][^3][^4]:

| Primitive | Role |
|-----------|------|
| **Agent** | Top-level unit. Holds instructions (system prompt), orchestration mode, channel publish settings, and a list of topics, knowledge sources, actions, and triggers. |
| **Topic** | A unit of conversation flow — a dialog tree of message, question, condition, variable, action, and redirect nodes. Activated by trigger phrases (classic) or topic descriptions (generative). |
| **Action / Tool** | How the agent does work outside pure conversation. Six surfaces: Power Automate flow, AI Builder prompt, Power Platform connector action, OpenAPI plugin, MCP tool, Azure Functions. |
| **Knowledge source** | Read-only grounding — SharePoint, public web, Dataverse, files, Microsoft Graph connectors, custom data sources. |
| **Trigger** | Utterance, event, schedule, or API call that kicks off a topic or autonomous run. |
| **Variable** | Named value with one of three scopes: `System.`, `Global.`, `Topic.`. |
| **Channel** | Surface where users meet the agent (Teams, M365 Copilot, web app, etc.). |

Three kinds of agent can be authored on this same primitive set[^1][^5]:

- **Custom (Copilot Studio) agent** — coordinates language models, instructions, knowledge, topics, tools, and triggers. Engages users across channels in multiple languages.
- **Autonomous agent** — a custom agent configured with **event triggers** instead of utterance triggers. Acts without user input, fired by external events, schedules, or business events from Dynamics 365. Event triggers consume Copilot Credits when they fire.
- The third option, **declarative agent**, is technically built outside Copilot Studio (Teams Toolkit + JSON manifest) but is part of the same agent-shape disambiguation — see [[declarative-agent]].

```
USER
 │
 │  user utterance | adaptive-card submit | event payload
 ▼
CHANNEL  (Teams | M365 Copilot | Web app | Direct Line | telephony)
 │
 ▼
AGENT  (custom Copilot Studio agent)
 │
 ▼
ORCHESTRATOR
 ├── classic ──► trigger-phrase match ──► single topic
 │
 └── generative ──► LLM planner picks N of:
                     │
                     ├── TOPIC          (dialog tree, Power Fx, slot filling)
                     ├── ACTION / TOOL  (flow | prompt | connector | MCP | code)
                     ├── KNOWLEDGE      (SharePoint | Dataverse | files | Graph | web)
                     └── NESTED AGENT   (agent-as-tool)
 │
 ▼
RESPONSE  (text | adaptive card | citations | follow-up Qs)
```

The orchestrator is the **single biggest architectural choice** for a Copilot Studio agent and has its own detailed entry — see [[generative-orchestration]][^6].

## Authoring

Three authoring surfaces[^1][^13][^14]:

1. **Web maker portal** at `copilotstudio.microsoft.com` — visual canvas for topics, knowledge sources, actions, and a built-in test pane. Tied to a Power Platform environment.
2. **Teams maker app** — same surface, embedded in Teams.
3. **`microsoft/skills-for-copilot-studio`** — a first-party Microsoft plugin that lets [[claude-code]], GitHub Copilot CLI, and VS Code author Copilot Studio agents as YAML, with schema validation, templates, and 30+ specialized skills covering authoring, lookup/validation, management, and evaluation[^13]. Templates exist for the five primitive kinds — `actions/`, `agents/`, `knowledge/`, `topics/`, `variables/` — and serve as canonical YAML starting points[^13].

The agent itself has a YAML representation that is canonical for both the plugin and the `pac copilot extract-template` command[^13][^14]. Agents (top-level metadata, instructions, channel publish settings, generative orchestration toggle), topics, knowledge-source references, variables, and actions can all be authored as code; the maker portal then becomes a *view* of the YAML rather than the source of truth[^13]. Some advanced flow steps and adaptive-card design remain visual-only; SharePoint indexing, being asynchronous, is not in YAML[^13].

Lifecycle commands exposed by the `pac copilot` CLI[^14]:

| Command | Purpose |
|---------|---------|
| `pac copilot extract-template --bot <id> --environment <id> --templateFileName <yaml>` | Export an existing agent as a YAML template. |
| `pac copilot create --templateFile <yaml>` | Create a new agent from a YAML template. |
| `pac copilot list` | List agents in environment. |

The older alias `pac virtual-agent` still appears in some Microsoft docs; both refer to the same command group post-rename[^14].

Every Copilot Studio agent lives **inside a solution** — the Power Platform packaging unit[^14]. Solutions wrap one or more agents plus their dependencies (flows, connection references, environment variables, Dataverse tables) and are exportable as a `.zip` (managed or unmanaged). Solutions are the unit of promotion across environments (dev → test → prod)[^14].

## Deployment and lifecycle

A Copilot Studio agent is shipped through environments and pipelines[^14][^15][^16]:

1. **Author** in dev — YAML or visual portal — and validate against the schema.
2. **Test pane** — live conversation in dev, with an **activity map** showing which topic, action, and knowledge source fired each turn[^15]. A conversation can be saved as an evaluation snapshot for later regression.
3. **Agent Evaluation** — a built-in eval framework with two test-set kinds: **single-response** (one user query → expected answer) and **conversational** (multi-turn scripted dialogue with assertions across turns)[^16]. Test methods include exact match, semantic similarity, and LLM-as-judge with a custom rubric. Test results are retained for **89 days** in-portal — export to CSV for longer retention[^16].
4. **Solution export** to a managed `.zip` and import to test, then prod, via a **Power Platform pipeline** (Microsoft's deployment automation product) or Azure DevOps with Power Platform Build Tools[^14]. Manual approval gates can be inserted before prod publish.
5. **Publish** the prod agent to its target channels.
6. **Monitor** via the in-portal analytics dashboard, the activity map, Application Insights, Microsoft Purview audit logs, and Microsoft Sentinel[^12].

Two source-control patterns are commonly used[^13][^14]:

- **Solution-export-to-git** — the traditional Power Platform ALM flow. Export → `pac solution unpack` → commit text. Re-pack and import on the receiving side.
- **YAML-first authoring** — using `skills-for-copilot-studio` (or `pac copilot create`) so that the YAML in git is the source of truth and the maker portal is a view of it[^13]. This pattern enables natural git diffs and PR review without `.zip` blobs in the repo.

## Cost and licensing

Copilot Studio billing changed currency on **2025-09-01** from "messages" to **Copilot Credits**[^7]. There is no change in the quantity per prepaid pack or to the pay-as-you-go rate[^7]. Three purchasing paths[^7][^8]:

| Path | Pricing | When |
|------|---------|------|
| **Capacity packs (prepaid)** | $200/month for 25,000 Copilot Credits | Predictable monthly load, committed. |
| **Pay-as-you-go (Azure)** | $0.01 per credit (effective $0.014/credit at premium tier) | Spiky / unpredictable usage. |
| **Pre-Purchase Plan (PPP)** | Annual commitment with up to 20% discount | High-volume, year-plus horizon. |

Different events consume different amounts of credits — categories include classic messages, generative messages, grounding (search/retrieval), actions, and premium events, where premium events can cost up to roughly 4× standard[^7]. A practical consequence: deterministic logic that can be expressed as a single MCP tool call should not be split into multiple generative-orchestration decisions, because each decision is a model call[^3][^6].

Users licensed for **Microsoft 365 Copilot** can interact with a Copilot Studio agent inside Microsoft 365 surfaces (Teams, BizChat) for certain event categories — classic, generative, grounding, actions — without consuming credits[^7][^20]. The exact list of "certain events" is documented in the official February 2026 Copilot Studio Licensing Guide[^20].

The terminology drift between "messages" and "credits" still appears in secondary sources[^7]. The canonical Microsoft Learn page is the authoritative rate sheet[^7].

## Governance

Copilot Studio inherits the Power Platform governance stack[^9][^10][^11][^12]:

- **Geographic data residency** follows the Power Platform environment region — supported geographies include Canada, the US, the UK, the EU, and 14 others under the **Multi-Geo subscription** and **Advanced Data Residency** programs[^9]. Each environment has its own region, its own DLP policy, and its own Dataverse instance.
- **Cross-region data movement caveat** — when an admin allows data movement across regions, prompts and outputs may move outside the chosen region to where a generative AI feature is hosted[^10]. For Copilot Studio generative features whose Azure OpenAI endpoint is not yet local, the admin must opt in to allow data movement for those features to work[^10]. The November 2025 Microsoft 365 in-country processing announcement applies to Microsoft 365 Copilot specifically and does not necessarily extend to Copilot Studio agents[^9].
- **Data Loss Prevention (DLP)** classifies Power Platform connectors into Business / Non-business / Blocked groups[^11]. A flow or agent cannot mix Business and Non-business connectors in the same context. Agent DLP enforcement has been mandatory tenant-wide since early 2025 (MC973179); the prior agent enforcement exemption is no longer supported[^11].
- **Microsoft Purview** receives every prompt and response from Copilot Studio interactions in the AI activities tab in DSPM and DSPM for AI[^12]. Sensitivity labels flow through into responses, and conversation transcripts can be retention-managed via Purview retention labels[^12].
- **Microsoft Sentinel** can ingest Power Platform audit events for SIEM correlation via the Office 365 connector plus Power Platform audit events[^12].
- **Customer-managed keys (CMK)**, **Customer Lockbox**, and **Microsoft Cloud for Sovereignty** are available on tenants in regulated industries but are not on by default[^11].

Six roles map onto these controls[^11]: **User** (talks to a published agent), **Maker** (builds in their environment), **Owner** (specific agent), **Environment admin** (DLP, capacity, env settings), **Copilot manager** (tenant-level oversight), **Tenant admin** (cross-tenant policy).

Two **Responsible AI** controls deserve specific attention for compliance-sensitive agents[^17]:

- **Citation enforcement** — generative-mode settings can suppress responses without citations, falling back to a default refusal phrase such as *"I'm sorry, I'm not sure how to help with that."*[^17].
- **Built-in Azure Content Safety filters** apply to every generative call and cannot be disabled[^17].

## Common Pitfalls

The platform's known sharp edges, as documented by Microsoft Q&A and community reports[^18][^19][^21]:

1. **PDF parsing is not built in.** A user attaching a PDF to a Copilot Studio agent gets a binary blob or URL stored as a variable, not parsed text[^18]. Any PDF-driven flow must add an explicit extraction step — an AI Builder prompt with structured-JSON output, a Power Automate flow with Azure Document Intelligence, or an MCP tool[^18].
2. **Generative-orchestration mis-routing between topics.** When two topics have overlapping descriptions, the orchestrator can jump between them on consecutive turns, or fall through to "Unknown intent" after a correct generative answer[^19][^21]. Mitigations include keeping topic descriptions disjoint (writing explicit *"NOT triggered when …"* clauses), disabling trigger evaluation inside sensitive flows, and avoiding streaming responses that fire trigger evaluation before generation completes[^19][^21].
3. **Conversational Boosting can overwrite a correct generative answer** when multiple knowledge sources conflict, the system topic firing after generative produces a degraded version[^21]. Mitigation: use a single knowledge source per topic, inspect the activity map, customize Conversational Boosting to short-circuit inside structured flows[^21].
4. **Adaptive Card + generative orchestration conflict** — a topic that uses an adaptive card can be re-evaluated by the orchestrator after submit, producing conflicting text alongside the form values[^21]. Mitigation: disable generative orchestration for card-based topics at the topic-level toggle and handle the adaptive-card flow deterministically[^21].
5. **Sub-agent / connected-agent ignoring instructions.** A parent agent calls a sub-agent that ignores its instructions; the most critical instructions need to be repeated in each sub-agent call, and sub-agents need to be tested in isolation before chaining[^21].
6. **Custom feedback widgets ignored under generative orchestration** — feedback topics never trigger because the user's last utterance does not look like feedback to the orchestrator. Mitigation: trigger feedback via an adaptive card with explicit submit, not a topic trigger[^21].

A general principle that follows from these patterns: keep deterministic logic out of generative orchestration where possible[^3][^21]. A 13-rule clause-flag engine should be a single MCP tool, not 13 separate orchestration decisions — both for correctness and for cost.

## See also

- [[declarative-agent]] — the simpler, manifest-only sibling that runs on Microsoft 365 Copilot's Sydney orchestrator instead of the Copilot Studio runtime.
- [[generative-orchestration]] — the LLM-driven topic/tool/knowledge selection mode that is required for MCP support and autonomous agents.
- [[copilot-studio-vs-azure-ai-foundry]] — head-to-head comparison of Copilot Studio against the pro-code Azure AI Foundry Agent Service for enterprise agent scenarios.
- [[claude-code]] — the AI coding assistant that, via the first-party `microsoft/skills-for-copilot-studio` plugin, can author Copilot Studio agents directly as YAML.
- [[anthropic]] — vendor of the Model Context Protocol that Copilot Studio supports as a first-class action surface in generative orchestration.
