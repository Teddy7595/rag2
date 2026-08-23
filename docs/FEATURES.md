# Features

Deep dives on the four pieces of RAG2 that don't fit in a paragraph or two in the root [README](../README.md): the engram/PAD identity system, the saga narrative-continuity system, the workshop feature, and the context traceability graph.

A note on scope: this document describes what's actually implemented and verifiable in the code, not the full design space that was explored while building the project. Where a feature has a documented but unimplemented "next step," that's called out explicitly rather than implied.

---

## Engrams & Affective State (PAD)

Each conversational identity ("engram") carries a small affective-state vector using the PAD model (**P**leasure, **A**rousal, **D**ominance) — a standard representation from affective computing, rather than a grab-bag of ad-hoc personality attributes (mood, empathy, etc. as disconnected fields).

**How it updates.** After every turn, `_compute_affective_delta` (`app/knowledge/application/service.py`) computes small deltas from the user's message, purely by deterministic rules:

- `pleasure` shifts from a small hardcoded lexicon of positive/negative Spanish words found in the user's text.
- `arousal` shifts from exclamation/question mark counts plus how long the reply was relative to its token budget.
- `dominance` shifts from a lexicon of dominant ("hazlo", "quiero que") versus submissive ("no sé", "tal vez") phrasing markers.

Each delta is clamped to a small range per turn, and the running state is updated with exponential retention (`pleasure * 0.9 + delta_p`, same for the other two axes), then clamped to `[-1, 1]`. The state persists per engram and is injected as explicit tone context on every generation call.

**Why deterministic instead of LLM-scored.** The header comment on the scoring function says it plainly: *"No extra LLM call per turn (hardware constraint)."* Scoring affect by asking a second model call would double inference cost per turn on hardware that's already VRAM-constrained (see the README's problem statement). The tradeoff is a coarser signal than an LLM-scored "importance" rating would give — but it's free, auditable (you can plot the P/A/D trajectory over time), and update failures never break a turn: `update_affective_state` is fire-and-forget and always returns a normal result even if persistence fails.

**What this is not.** Early design notes for this project explored a much larger surface: a memory stream with recency/importance/relevance scoring (à la *Generative Agents*, Park et al. 2023), a "reflection" layer that periodically synthesizes higher-level insights from raw observations, and a per-engram autonomous background loop that lets an identity "act" between user turns. **None of that is implemented.** There's no memory-stream scoring, no reflection layer, and no autonomous/daemon loop anywhere in the codebase — engrams only update their affective state in direct response to a turn, never in the background. The PAD vector itself is the one piece of that exploration that shipped.

---

## Sagas (narrative continuity)

Sagas are the `operations` module's tool for structured, multi-part storytelling tied to an engram persona — closer to a lightweight continuity tracker than a full narrative-planning engine.

**Domain model.** A `SagaWorkflow` holds `title`, `premise`, `summary`, `status`, `world_building`, and two logs: `command_history` (a flat list of free-text narrative "commands") and `act_history` (a structured log of `{kind, act_id, phase, ...}` entries). There's no separate `Act`/`Scene`/`Character` domain entity — acts are inferred from text convention (`[ACT N OPEN]`, `[ACT N CLOSE]`, `[ACT N SUMMARY]`) parsed out of `command_history` with a regex, not modeled as first-class relational objects.

**What it actually does:**

- **Sliding context window with deep recall** (`build_saga_next_context`): a configurable window (2–24 commands, default 6) of recent history, plus a token-overlap deep-recall pass that pulls in older commands referenced by the current prompt but outside the window.
- **Consistency checking** (`analyze_saga_consistency`): two lightweight heuristics, not a coherence-reasoning engine — a hardcoded list of contradictory keyword pairs (`vive`/`muere`, `aliado`/`enemigo`, `gana`/`pierde`, `paz`/`guerra`, `humano`/`inmortal`) searched by substring across all commands, plus a simple per-entity timeline check (capitalized words treated as entity names, tracked on two binary axes — alive/dead, allied/enemy — flagging flips over time). The resulting `coherence_score` is a linear combination of how many of each contradiction type were found.
- **Retcon** (`apply_saga_retcon`): appends a templated correction suggestion based on the first detected contradiction's type — an append-only suggestion, not an automatic rewrite of prior content.
- **Debate** (`debate_saga`): records a single debate pass and can optionally persist it as a `knowledge` entry tagged to the saga and engram, so it's retrievable in normal chat later.

**What's designed but not built.** The original spec for this feature (question-driven scenario seeding, first-class editable acts/scenes/characters/world-rules, automatic act-closing summaries, and a full self-correction rewrite loop) goes further than the current implementation. Concretely: there's no guided seed questionnaire (all saga fields are free text at creation), no structured act/scene/character entities (everything lives in the command-history text), and act summaries must be typed in manually as a tagged command rather than generated automatically on close.

---

## Workshop (scoped RAG sessions)

A workshop is a chat session whose knowledge retrieval is scoped to a hand-picked subset of already-ingested documents, with an explicit path to promote what came out of it into the main knowledge base.

**Creating one**: the user picks an engram and checks a subset of documents already ingested into the global `knowledge` index (the creation form calls `GET /api/knowledge/documents` and stores just their `{uri, title}` pairs — a workshop never holds its own separate document store).

**How the scoping works**: a `WorkshopSession` links a `chat_session_id` to that list of document URIs. During a turn, `app/interaction/application/realtime.py` checks whether the active chat session belongs to a workshop and, if so, passes the workshop's document URIs as a `source_filter` into the context pipeline. `ContextRetrieverRuntime` then calls `list_by_sources(source_filter)` instead of `list_all()` — so scoping is a retrieval-time filter over the same global index, not a separate database or index.

**Promoting to general knowledge**: promotion isn't a copy or re-embedding of the workshop's underlying entries. The user writes (or pastes) a summary in a modal; `WorkshopService.promote` ingests *that summary text* as a brand-new document into the main `knowledge` index — through the same ingestion pipeline as any other document (chunking, embedding, page metadata) — titled `"[Workshop] {summary title}"` and tagged `workshop, promoted`. The resulting document/chunk IDs are recorded on the session, and its status moves from `active` to `promoted`.

**Full flow**: create workshop (engram + document checkboxes) → chat inside that scoped session → close it (`status → closed`, no side effects beyond that) → optionally promote (write a summary → ingested as a new document) or just delete it.

---

## Context Graph & Traceability

Every context-building call can also produce a graph via `POST /api/knowledge/context/graph`, giving you an explicit, inspectable record of what fed into a given response instead of a black box.

**Node types**: `query` (the raw query text, one per graph), `identity` (the resolved engram, if any), `knowledge` (one per retrieved knowledge fragment), and `engram` (one per referenced engram match).

**Edges and weights**:
- `query → identity`, relation `resolved_identity`, fixed weight `1.0`.
- `query → knowledge:X`, relation `retrieved_context`, weight = the retrieval score (a blend of lexical token match and embedding cosine similarity, computed in the context pipeline's scoring function) plus a `+0.5` bonus for the single top-ranked match, floored at `0.1`.
- `identity → engram:Y`, relation `persona_reference`, weight = the match score, floored at `0.1`.

**Primary/secondary topics**: `primary_topic` is the label of the top knowledge match (or the first query keyword if nothing matched); `secondary_topics` are the labels of the next three distinct matches. This is a simple "first vs. next three" heuristic, not topic clustering.

**In the admin panel**: [`/admin/context-graph`](SETUP.md#admin-panel) lets you fire a query and inspect the resulting nodes/edges as a plain list/table — there's no rendered graph visualization (no canvas/SVG layout) today, just the structured data. [`/admin/context-traces`](SETUP.md#admin-panel) gives a filterable, session/trigger-scoped view over past retrieval traces for auditing what happened on a given turn.

This graph is the audit layer, not the retrieval mechanism itself — see the root README's [Context retrieval system](../README.md#4-context-retrieval-system) section for how retrieval and Parent Document Retrieval actually work. Extending this into a hierarchical, community-summarized graph (clustering retrieved entities and retrieving from summaries first) is on the [roadmap](../README.md#8-roadmap), not yet built.
