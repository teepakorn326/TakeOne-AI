# TakeOne AI: MVP architecture and delivery plan

## Product boundary

TakeOne records production decisions and their economics. It does not edit video or autonomously produce a drama. A studio should be able to trace every accepted shot back to its attempts, review decisions, provider, and charged amount.

## System architecture

```text
Next.js web (Cloud Run) ──HTTP──> FastAPI (Cloud Run) ──> Cloud SQL PostgreSQL
                                  │                     └─ pgvector extension reserved
                                  ├──> Temporal workflows + worker
                                  ├──> VideoProvider adapters
                                  ├──> GCS signed media URLs
                                  └──> Secret Manager (provider keys)
```

One FastAPI application owns production state, review, routing, and cost calculations. A separate worker process executes Temporal workflows using the same domain modules. PostgreSQL is the source of truth; Temporal coordinates slow jobs but is never the source of production state. Media bytes live in GCS; database rows hold object keys and metadata. Provider credentials stay server side. FFmpeg is limited to media inspection, thumbnail creation, and necessary transcoding. The Production Assistant is optional and produces suggestions for a human to confirm; it cannot change workflow state.

The useful seams are `VideoProvider` (real providers and a mock), `PromptCompiler` (provider prompt formats), and the cost ledger (attempt charges and derived reporting). Each interface hides vendor or accounting details from production code. Services remain modules inside one deployable API until a real scaling need appears.

## PostgreSQL schema

All primary keys are UUIDs. Timestamps are UTC `timestamptz`. Money is `numeric(12, 4)` in USD; no floating point money. Child rows are reached through a workspace-owned series, and every read/write must check that path. `workspace_id` is repeated on audit/ledger rows for efficient scoped analytics, with database foreign keys preserving the relationship. Unique sequence constraints prevent duplicate episode, scene, shot, and attempt numbers.

| Table | Important columns and constraints |
| --- | --- |
| `workspaces` | `id`, `name`, `created_at` |
| `users` | `id`, `workspace_id`, `name`, `email`, `role`, `created_at`; unique `(workspace_id, email)` |
| `series` | `id`, `workspace_id`, `title`, `description`, `genre`, `status`, `created_at` |
| `episodes` | `id`, `series_id`, `episode_number`, `title`, `status`; unique `(series_id, episode_number)` |
| `scenes` | `id`, `episode_id`, `scene_number`, `description`, `location`, `time_of_day`; unique `(episode_id, scene_number)` |
| `shots` | `id`, `scene_id`, `shot_number`, `description`, `shot_type`, `duration_seconds`, `number_of_characters`, `dialogue_present`, `object_interaction`, `motion_complexity`, `camera_motion`, `quality_threshold`, `budget_limit`, `status`; unique `(scene_id, shot_number)` |
| `characters` | `id`, `series_id`, `name`, `description`, `visual_reference_url`, `notes`; unique `(series_id, name)` |
| `character_states` | `id`, `character_id`, `episode_start`, `episode_end`, `hairstyle`, `wardrobe`, `injury_state`, `props`, `notes`; validate ranges |
| `shot_specs` | `shot_id` unique FK, `character_ids` JSON, `location`, `action`, `dialogue`, `continuity_notes`, `version`, `updated_at`; overlapping shot requirements stay canonical in `shots` |
| `generation_attempts` | `id`, `shot_id`, `provider`, `model`, `prompt`, frozen `shot_snapshot`, `attempt_number`, unique `idempotency_key`, `status`, `provider_job_id`, `output_url`, `output_media_type`, `estimated_cost`, `actual_cost`, `cost_kind`, `generation_time_seconds`, `error_message`, `created_at`, `completed_at`; unique `(shot_id, attempt_number)` and provider job identity when present |
| `reviews` | `id`, `generation_attempt_id`, `reviewer_id`, `decision`, `failure_reason`, `notes`, `created_at`; one final review per attempt; reject requires reason |
| `cost_events` | `id`, `workspace_id`, `series_id`, `shot_id`, `generation_attempt_id`, `provider`, `model`, `operation`, `amount_usd`, `amount_kind`, unique `event_key`, `created_at`; unique event identity prevents double charging |
| `routing_decisions` | `id`, `shot_id`, `spec_version`, `provider`, `model`, `reason`, `estimated_cost`, `confidence`, `rule_version`, `is_mock`, `created_at` |

`shot_specs`, `routing_decisions`, `characters`, and `character_states` arrived in Phase 5. A shot spec read assembles its base requirements from `shots` and additional detail from `shot_specs`. Changing either increments the saved spec version. Each structured generation freezes the assembled spec and applicable episode state in `shot_snapshot`; it also records `prompt_source` and optional `creative_direction`. `generation_attempts` and `cost_events` arrived in Phase 2; `reviews` arrived in Phase 3. Store provider status as a constrained string, not a PostgreSQL enum, so adding a vendor state does not require enum surgery. Future embeddings use pgvector in a separate migration when there is a concrete retrieval requirement.

The spec editor sends `expected_version` so a stale editor receives a conflict instead of overwriting another saved version. Once a spec exists, generation accepts creative direction and compiles the prompt on the server; a manually supplied prompt is rejected for that shot.

## HTTP interface

JSON under `/api/v1`. Every normal request carries a real workspace identity and an authorized user identity. Phase 1 uses explicit local-only headers (`X-Workspace-Id`, `X-User-Id`) as a development placeholder; production must replace that dependency with verified identity before deployment.

| Phase | Endpoints |
| --- | --- |
| 1 | `POST /workspaces` (local bootstrap), `GET /workspaces/current`; `POST/GET /series`, `GET/PATCH /series/{id}`; `POST/GET /series/{id}/episodes`, `GET/PATCH /episodes/{id}`; `POST/GET /episodes/{id}/scenes`, `GET/PATCH /scenes/{id}`; `POST/GET /scenes/{id}/shots`, `GET/PATCH /shots/{id}` |
| 2 | `GET /shots/{id}/estimate`, `POST /shots/{id}/attempts` (requires `Idempotency-Key`), `GET /shots/{id}/attempts`, `GET /attempts/{id}`, `GET /attempts/{id}/cost-events`, `POST /attempts/{id}/cancel`, `GET /settings/providers` |
| 3 | `GET /review`, `GET /review/failure-reasons`, `POST /attempts/{id}/reviews`, `POST /shots/{id}/retry`; retry may override provider, model, and prompt |
| 4 | `GET /dashboard`, `GET /analytics/providers`, `GET /analytics/failures`, `GET /analytics/episodes`, `GET /analytics/series/{id}` |
| 5 | `PUT/GET /shots/{id}/spec`, `POST /shots/{id}/recommendation`, `GET /shots/{id}/recommendations`, create/list characters under `/series/{id}/characters`, edit/delete under `/characters/{id}`, and create/list/edit/delete states under `/characters/{id}/states` and `/character-states/{id}` |

Writes use idempotency keys where a duplicate request would spend money. Pagination is required for production lists and attempt/review feeds before real studio data is imported. Every identifier is checked against the active workspace, including indirect episode/scene/shot paths.

## ShotSpec and provider interface

```text
ShotSpec {
  shot_type, duration_seconds, character_ids[], location, action,
  dialogue, camera_motion, motion_complexity, object_interaction,
  quality_requirement, continuity_notes, budget_limit_usd
}

VideoProvider {
  capabilities() -> supported models, limits, pricing dimensions
  estimate_cost(spec, model) -> USD estimate
  generate(spec, compiled_prompt, model, idempotency_key) -> provider job id
  get_status(job_id) -> queued/running/succeeded/failed + output reference
  cancel(job_id) -> cancellation result
}

PromptCompiler.compile(spec, provider, model) -> provider-specific prompt
```

The current registry has two configurations of `MockVideoProvider`, with distinct names and simulated pricing, to exercise provider switching without paid calls. Phase 5's deterministic compiler formats them differently and includes selected characters' applicable episode state. The rule router uses shot motion, interaction, close dialogue, provider duration, and shot budget; each decision records a spec version, reason, estimate, and low confidence. It demonstrates routing mechanics and makes no quality claim about mock providers. One real adapter can be selected after checking studio demand and provider access. A second real adapter is added for comparison. The conceptual `ProviderAAdapter` and `ProviderBAdapter` are slots, not fake integrations. Future real-provider output is imported to GCS and exposed through expiring signed URLs. Credentials, provider response formats, and pricing policies stay inside adapters.

## Temporal workflow

`GenerateShot(attempt_id)` loads the attempt's frozen shot snapshot/prompt/model, submits with an idempotency key, polls status with a bounded interval and timeout, and records a cost event and output. It updates the attempt to `review` or `failed`. Temporal activities retry; a persisted provider job is reused on replay. The mock returns a sample frame and simulated cost, with no GCS import. The real-provider adapter will import video to GCS and issue signed URLs. Cancellation is a workflow signal. Human review is a separate durable application transaction: one immutable decision per attempt, with a required reason for rejection. The shot moves to `accepted` or `rejected`; a rejected shot can be edited and retried, creating a **new** attempt and workflow with a frozen new snapshot and optionally another provider. Workflow and database operations tolerate repeated activities.

## Cost definitions

Only chargeable `cost_events` are summed. Every amount is nonnegative USD; adjustments, if needed, will have explicit event types and audit links. Phase 2 records one final event per completed mock generation with `amount_kind=simulated`. Future adapters can record `actual` or provisional `estimated` amounts. The event key prevents duplicate charges when an activity runs again.

- **Total spend:** sum of generation cost events in scope, including rejected, pending, and accepted attempts.
- **Retry waste:** sum of costs associated with attempts whose final review is `rejected`. This is a subset of total spend, not an additional charge.
- **Cost per accepted shot (CPAS):** total spend ÷ count of distinct shots with an accepted attempt. Show `—` when the denominator is zero. Scope and as-of time must be visible.
- **First-pass acceptance:** distinct shots accepted on attempt 1 ÷ distinct shots with a final review of attempt 1.
- **Retries per shot:** sum of `max(attempt_count - 1, 0)` ÷ shots with any attempt.
- **Provider acceptance rate:** accepted reviewed attempts ÷ all reviewed attempts for that provider; pending attempts stay out of this rate.
- **Provider cost per accepted shot:** all spend on that provider ÷ distinct shots accepted from that provider. It includes that provider's rejected attempts, but mixed-provider retries make this a provider-attributed metric rather than the full journey cost of those shots.
- **Average attempt cost:** provider spend ÷ chargeable attempts.
- **Cost per attempted shot:** total generation spend ÷ distinct shots with at least one generation attempt. Draft shots do not lower this average.

Dashboard comparisons must use the same date/scope and clearly label estimates versus actual charges. The opening example can be shown only when sourced from real recorded attempts; avoid hardcoded claims.

Phase 4 implements these definitions in `analytics.py`. Each report uses one workspace or one workspace-owned series, includes its computation time, and reports simulated, actual, and provisional estimated amounts separately. Only generation cost events enter these metrics; other ledger operations stay separate. `GET /dashboard` returns all UI sections with one scope; the narrower analytics endpoints expose provider, failure, and episode slices. A missing denominator is `null` in JSON and `—` in the UI. The current dashboard is a live aggregation of recorded events and reviews, with no cached or hardcoded performance claims.

## MVP user journey

An owner creates a workspace and series, adds episodes, scenes, and shots, and marks a shot ready. A producer completes a structured ShotSpec, sees a provider recommendation and estimate, then submits. The attempt advances through generating to review. A reviewer watches the signed video URL beside requirements, continuity, and prior attempts, then accepts or rejects with a required reason. On rejection, they retry or switch provider. The dashboard recomputes spend, waste, first-pass acceptance, and CPAS from recorded state.

## Major risks and controls

1. **Provider billing is delayed or inconsistent.** Save estimated and actual separately; use idempotent ledger event identities; show estimate status.
2. **A provider succeeds while polling fails.** Persist provider job ID before polling; resume from that job ID rather than generating again.
3. **Provider output and signed URLs expire.** Import durable media to GCS, store object key, issue fresh short-lived URLs on access.
4. **Workspace data leakage.** Scope every query by workspace and test indirect resource paths; replace development headers with verified identity before any public deployment.
5. **Concurrent retry requests create duplicate attempts.** Lock the shot row or use transactional sequence allocation and an idempotency key.
6. **Provider comparison can mislead on small samples and shot complexity.** Show counts and shot categories alongside cost; treat rule confidence as heuristic.
7. **Temporal and Cloud Run worker lifecycle.** Run the worker as an always-on process suitable for long polling; validate Cloud Run configuration and costs before deployment.

## Dependency-ordered backlog

1. **Phase 1:** repo setup; PostgreSQL, migrations, workspace/user bootstrap, scoped series/episode/scene/shot endpoints; minimal production planning UI; tests for hierarchy, uniqueness, and workspace isolation.
2. **Phase 2:** provider seam and mock; attempt lifecycle, idempotent cost ledger, Temporal worker, media storage contract, generation UI; test attempt numbering and failure/timeout recovery.
3. **Phase 3:** review queue, immutable accept/reject record, required failure reason, retry/provider switch, media preview; test transitions and duplicate review prevention.
4. **Phase 4:** cost query module, CPAS, retry waste, acceptance rates, provider and episode reports; test formulas with mixed-provider and pending cases.
5. **Phase 5:** ShotSpec, compiler, continuity metadata, versioned rule router, stored recommendations; test routing and budget rules.
6. **Pilot readiness:** verified authentication, billing reconciliation, observability, backups, retention, pagination, basic role permissions, and one real provider integration. Validate savings and willingness to pay with a studio pilot.
