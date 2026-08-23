# Saga Feature Requirements

## Purpose

Define the real product requirements for the Saga feature as a first-class storytelling workspace, tightly integrated with chat memory and engram personas.

## Product Intent

Saga is not a simple note-taking tool. It is a narrative engine that:

- builds complete stories with high coherence,
- asks for missing information to seed the scenario,
- tracks and reasons over plot/space/characters,
- supports iterative debate and revision,
- persists state that can be referenced in normal chat,
- self-corrects when output drifts from user intent.

## Core Requirements (Authoritative)

### R1. Full-story authoring with cross-chat recall

- Saga must support creating complete stories (acts, scenes, summaries, world rules).
- Saga entities and outcomes must be mentionable in regular chat and retrievable via context pipeline.
- Chat responses should be able to reference relevant saga facts without exposing internal labels.

### R2. Guided scenario seeding (question-driven)

- Saga must actively ask the user the minimum required questions to construct a valid seed scenario.
- Required dimensions: genre, tone, setting, timeline constraints, POV, key conflict, cast, stakes.
- The system must keep asking only unresolved dimensions until seed is complete.

### R3. Coherence reasoning engine

- Saga must enforce consistency across:
  - spatial logic (where things can happen),
  - timeline/order of events,
  - character identity, motivations, and state transitions,
  - causal continuity of plot.
- Before committing a new act/scene, Saga must run a consistency pass and emit warnings/repair proposals.

### R4. Editable structure (mutable Saga)

- Users must be able to add, update, delete, and reorder Saga pieces:
  - acts,
  - scenes,
  - characters,
  - world rules,
  - canonical facts.
- Changes must keep revision history and preserve recoverability.

### R5. Debate loop before/after act finalization

- Users can open a debate phase before closing an act.
- Users can reopen debate after closure to retcon/adjust continuity.
- Debate output can be persisted as inspirational memory and linked to the corresponding saga_id and act_id.

### R6. Automatic act summarization for continuity

- On act closure, Saga must generate a canonical summary of the previous act.
- The next act prompt context must include that summary by default.
- Summary must be compact, stable, and optimized for continuity.

### R7. Sliding context window + deep recall fallback

- Saga runtime must use a sliding active window for low-latency continuity.
- If a new turn references information outside the window, system must retrieve older canonical facts from storage/index.
- Retrieval strategy must prioritize canonical summaries and confirmed facts over raw dialogue.

### R8. Self-correction (chat + saga)

- Both chat and saga pipelines must detect output that violates user intent, style constraints, or canonical facts.
- On violation, system should attempt one controlled rewrite pass before fallback.
- Quality telemetry must record correction trigger, reasons, and outcome.

### R9. Smartphone accessibility

- Saga management and debate flows must be reachable from mobile browsers.
- Admin access policy must allow the selected Saga UI routes remotely when configured.
- UI must remain usable on narrow viewports (responsive controls, no desktop-only dependencies).

## Functional Scope

### Saga Domain Objects

- `Saga`
- `Act`
- `Scene`
- `CharacterProfile`
- `WorldRule`
- `CanonicalFact`
- `DebateRecord`
- `ConsistencyReport`

### Minimum Operations

- Create saga from guided seed wizard.
- Append/update/delete acts and scenes.
- Run consistency analysis.
- Run debate pass and optionally persist memory.
- Close act and generate canonical summary.
- Retcon with explicit apply/no-apply path.

## Integration Requirements

### Chat Integration

- Context retrieval must include saga artifacts when relevant.
- Chat response must reference saga naturally (no internal tags or implementation jargon).

### Knowledge/Operations Integration

- Saga summaries and canonical facts should be queryable in context APIs.
- Operations events must expose status/audit for saga lifecycle actions.

## Non-Functional Requirements

- Coherence checks should complete within interactive latency budget for normal act sizes.
- Saga edits must be durable and auditable.
- Mobile UX must support create/edit/debate without requiring desktop.
- Guardrails/sanitization must remove internal prompt leakage.

## Acceptance Criteria

### AC1. Scenario seed completeness

- Given a new saga with missing seed fields,
- when user starts creation,
- then system asks only unresolved required questions until seed is complete.

### AC2. Act continuity

- Given Act N is closed,
- when Act N+1 starts,
- then Act N canonical summary is included in context baseline.

### AC3. Out-of-window recall

- Given user references an early act detail outside sliding window,
- when generating response,
- then system retrieves and uses canonical fact before final output.

### AC4. Debate loop

- Given an act (open or closed),
- when user requests debate,
- then debate record is created and optionally persisted to memory.

### AC5. Self-correction

- Given a model output that violates constraints,
- when immersive/quality gate runs,
- then system rewrites once and only falls back if rewrite still fails.

### AC6. Mobile access

- Given remote smartphone client,
- when requesting configured Saga UI route,
- then route is accessible if present in remote admin allowlist.

## Delivery Phases

### Phase 1 (Now)

- Guided seed questionnaire
- Act model + canonical summary
- Debate before/after act
- Sliding window + deep recall baseline
- Mobile-accessible Saga entry routes

### Phase 2

- Advanced coherence graph checks (space/time/character)
- Rich retcon workflow with impact preview
- Full Saga UI workspace (`/admin/sagas`) with responsive layout

### Phase 3

- Adaptive planning for long-form stories
- Multi-engram collaborative debate
- Automated continuity stress tests
