---
title: Declarative Agent
created: 2026-05-29
last_updated: 2026-05-29
sources:
  - id: 1
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/overview-declarative-agent
    title: Microsoft Learn — Overview of declarative agents
  - id: 2
    type: web
    ref: https://www.voitanos.io/blog/microsoft-365-copilot-developers-guide-declarative-agents-webinar-recap-20260415/
    title: Voitanos — M365 Copilot Developers Guide, Declarative Agents
  - id: 3
    type: web
    ref: https://stevecorey.com/breaking-down-copilot-agents-declarative-agents-vs-custom-engine-agents/
    title: Steve Corey — Declarative agents vs custom engine agents
  - id: 4
    type: web
    ref: https://imrizwan.com/blog/building-copilot-declarative-agents-teams-toolkit
    title: imrizwan — Building declarative agents with Teams Toolkit
  - id: 5
    type: web
    ref: https://learn.microsoft.com/en-us/microsoft-copilot-studio/publication-fundamentals-publish-channels
    title: Microsoft Learn — Publishing channels in Copilot Studio
  - id: 6
    type: web
    ref: https://www.voitanos.io/blog/microsoft-365-copilot-evaluate-your-agent-options-webinar-recap-20260408/
    title: Voitanos — Evaluate your M365 Copilot agent options
  - id: 7
    type: web
    ref: https://www.reddit.com/r/copilotstudio/comments/1md3sj9/declarative_agents_are_so_much_better/
    title: Reddit r/copilotstudio — Declarative agents anecdote
  - id: 8
    type: builtin
    title: Microsoft public documentation synthesis (Copilot Studio research, 2026-05-29)
  - id: 9
    type: builtin
    title: Reddit r/copilotstudio community reports (low-confidence anecdotal)
confidence_level: high
---

# Declarative Agent

## Definition / Overview

A **declarative agent** is a manifest-driven extension of Microsoft 365 Copilot — a constrained Copilot persona scoped to a specific set of instructions, knowledge sources, and actions, with **no custom orchestration logic**[^1][^8]. It is defined entirely by a JSON manifest plus optional companion files (instructions, action plugins, knowledge bindings) and runs on Microsoft's first-party **Sydney orchestrator** — the same orchestrator powering first-party Microsoft Copilot agents such as Researcher, Analyst, and Knowledge[^2][^3]. New Microsoft 365 Copilot capabilities tend to land on this surface first[^2].

Declarative agents are typically authored in VS Code with the **Teams Toolkit**[^1][^4]. Developers do not write code that handles user turns; they write a manifest and let Microsoft own the conversation loop. Community feedback emphasizes the consequences of this trade-off in both directions: a Reddit anecdote describes the surface as *"far more engaging, nicely formatted… knowledge retrieval was much better"* than a Copilot Studio custom agent for knowledge-only scenarios[^7][^9], while practitioners working on multi-step business workflows note that the absence of custom logic disqualifies declarative agents whenever deterministic rules or branching flows are needed[^3][^8].

The platform context for the term: Microsoft splits its agent-extensibility surfaces into two shapes — **declarative agents** (Sydney-hosted, manifest-only) and **custom engine agents** (third-party-hosted, full code, usually built with [[copilot-studio]] or the M365 Agents SDK)[^3][^8]. The two are not mutually exclusive within a tenant, but for any given user-facing scenario they are an either/or choice.

## Architecture / Design

A declarative agent is a thin descriptor over the Microsoft-owned orchestrator[^1][^3][^8]:

```
USER  (in Microsoft 365 Copilot — BizChat, Teams sidebar, …)
 │
 ▼
SYDNEY ORCHESTRATOR  (first-party, owned by Microsoft)
 │
 │  reads:
 │    • declarative-agent manifest
 │    • instructions
 │    • knowledge sources (SharePoint, Graph, OneDrive, web, files)
 │    • actions (API plugins from OpenAPI specs)
 │
 ▼
RESPONSE  (text + citations, optional adaptive cards via actions)
```

The agent's **shape** is fully declared, never coded[^1][^3]. Microsoft's runtime decides which knowledge source to retrieve from, which action to call, when to ground, when to compose a response, and when to escalate. This is the same orchestrator that powers Microsoft's own first-party copilots, so declarative-agent UX behavior tracks the latest Sydney capabilities automatically[^2][^8].

The manifest's contract surface, expressed in compact form[^1][^3][^4]:

| Slot | Purpose |
|------|---------|
| **Name + description** | How users discover and disambiguate the agent in the BizChat agent picker. |
| **Instructions** | Plain-language system prompt. Tone, persona, constraints, escalation rules. |
| **Capabilities** | Declarations that Microsoft's orchestrator reads to decide which features it can use (e.g., web search, code interpreter, image generation — subject to feature availability and license). |
| **Knowledge sources** | SharePoint sites or libraries, OneDrive folders, Graph connectors, files, public web. Permission-trimmed via Microsoft 365 ACLs. |
| **Actions** | Optional API plugins, defined by an OpenAPI spec, that the orchestrator can invoke when it judges them relevant. |
| **Behavior toggles** | A small set of platform-level switches (e.g., starter prompts, response style preferences). |

There is **no place** in this contract to hold a multi-step state machine, a deterministic rule engine, a custom retrieval pipeline, or a Power Fx expression. If the scenario needs any of those, the right shape is a [[copilot-studio]] custom agent, not a declarative agent[^3][^8].

## Manifest Structure

A declarative agent project authored in Teams Toolkit typically contains the following files[^1][^4]:

```
my-agent/
├── appPackage/
│   ├── manifest.json              # Teams app manifest (host shell)
│   ├── declarativeAgent.json      # the declarative-agent manifest itself
│   ├── instructions.txt           # plain-language system prompt
│   └── color.png, outline.png     # icons
├── plugins/                       # optional API plugin OpenAPI specs
│   └── <plugin>.json
└── env/, infra/                   # Teams Toolkit deployment configs
```

The **`declarativeAgent.json`** carries the agent's substance: its display name and description, its instructions file reference, its declared knowledge-source bindings, its action plugins, and its capability declarations[^1][^4]. Edits to this file map to behavioral changes; there is no companion code module that Microsoft would rebuild.

Deployment is via the Teams Toolkit publish flow (developer tenant → admin approval → broader rollout), or via the **Microsoft 365 Agents Toolkit** for organization-wide distribution[^1][^4][^6]. Tenant admins control which declarative agents are deployable through the same M365 admin tooling that governs Teams apps and Microsoft 365 Copilot extensibility[^6][^8].

## Capabilities

The capability surface tracks Microsoft 365 Copilot's first-party features and grows with the platform[^1][^2][^8]:

- **Knowledge grounding** over SharePoint sites or document libraries, OneDrive folders, Graph connectors (for non-SharePoint org content), specific uploaded files, and public web content. Permission-trimmed automatically — a user never sees content they would not see in a normal SharePoint search[^1].
- **Citations** in responses, generated by the Sydney orchestrator and rendered consistently with first-party Copilot agents[^1][^2].
- **API plugin actions** — invoke an external HTTP API described by an OpenAPI spec. The orchestrator decides when to call the action and how to map user intent to its parameters[^1][^4].
- **Adaptive-card responses** rendered by the host (Teams, BizChat) when the orchestrator chooses a card-shaped reply[^1].
- **Starter prompts** — author-provided suggestions that appear in the agent's first-run UI to seed conversation[^1][^4].
- **Tenant + permission scoping** — admins can restrict deployment to specific Microsoft 365 groups, regions, or pilot user sets[^6][^8].

What it does **not** offer[^3][^8]:

- Custom orchestration. The agent cannot decide its own turn-by-turn behavior; Microsoft owns that loop.
- Persistent variables across turns beyond what the orchestrator's session state holds.
- Power Fx expressions, deterministic conditions, slot-filling state machines, or multi-step branching dialogs.
- Power Automate flow integration as a first-class node (an API plugin can call a flow's HTTP trigger, but that is the agent calling out to a flow, not embedding flow logic inside the agent).
- Channel reach beyond Microsoft 365 Copilot surfaces — declarative agents do not publish to Power Pages, Direct Line, telephony, or arbitrary web apps[^5][^8].

## Limitations vs Custom Agents

The decisive line between declarative agents and Copilot Studio custom agents is **where the orchestrator runs**[^3][^5][^8]:

| Dimension | Declarative agent | Custom Copilot Studio agent |
|-----------|------------------|----------------------------|
| Orchestrator | Sydney (Microsoft, first-party) | Copilot Studio runtime (custom + [[generative-orchestration]] or classic) |
| Custom logic | None — manifest only | Yes — topics, Power Fx, flows, MCP, custom code |
| Channel reach | Microsoft 365 Copilot only (BizChat, Teams sidebar) | Many — Teams, M365 Copilot, SharePoint, Power Pages, Web app, telephony, Direct Line, etc. |
| Authoring | Teams Toolkit + JSON manifest | Web maker portal, Teams maker app, or YAML via `microsoft/skills-for-copilot-studio` |
| Cost shape | Bundled in the M365 Copilot license (~$30/user/month) | Variable per Copilot Credit, or PAYG, with M365 Copilot license waiving credits for some in-M365 events |
| Time to first usable agent | 1–3 weeks for a knowledge-grounded scenario | 4–8 weeks for production-quality custom logic |
| Tightness in BizChat UI | High (first-party orchestrator integration) | Custom-agent path can publish to the M365 Copilot channel but does not run on Sydney; some UI integration is more limited |
| Lock-in | High — works only inside M365 Copilot | High to Power Platform but multi-channel |

**Disqualifying scenarios for declarative agents** (i.e. cases where the right answer is a [[copilot-studio]] custom agent or a different shape entirely)[^3][^8]:

1. The agent must run a deterministic rule engine — for example, 13 clause-classification rules whose output must be reproducible byte-for-byte across runs.
2. The agent owns a multi-step workflow with conditional branching, slot filling, or human-in-the-loop approvals that cannot be expressed as a single API plugin call.
3. The agent must surface outside Microsoft 365 — embedded in a public web app, a customer-facing chat, telephony, or anything Direct Line.
4. The agent must use the **Model Context Protocol** as a first-class action surface — MCP support is gated to Copilot Studio's [[generative-orchestration]] mode and is not part of the declarative-agent manifest[^8].
5. The agent must own its conversation memory beyond what the orchestrator's session state provides.

**Right-fit scenarios for declarative agents**[^1][^2][^7]:

- A persona-scoped knowledge-Q&A agent over a specific SharePoint library — for example, an "HR Policy Assistant" that answers from the HR policy library only.
- An agent that surfaces a single OpenAPI-described internal API as a Copilot tool — e.g., a helpdesk agent that can open a ticket via a back-office API.
- A first-party-feeling extension of Microsoft 365 Copilot that shares the visual polish of Researcher / Analyst / Knowledge[^2].
- A scenario where the team would otherwise build something custom but only needs the orchestrator's defaults plus a knowledge binding — declarative agents minimize the surface to maintain.

The core mental model is that a declarative agent is to Microsoft 365 Copilot what a Chrome extension is to Chrome — declared shape, hosted runtime, restricted by what the host exposes[^1][^3][^8].

## See also

- [[copilot-studio]] — the platform whose **custom agent** path is the alternative when declarative-agent constraints become disqualifying.
- [[generative-orchestration]] — the Copilot Studio orchestration mode that custom agents adopt when they need multi-intent reasoning, MCP support, or autonomous behavior; declarative agents have nothing analogous because Microsoft owns their orchestration loop.
- [[copilot-studio-vs-azure-ai-foundry]] — when even Copilot Studio's custom agent is too constrained, the comparison continues into Azure AI Foundry territory.
