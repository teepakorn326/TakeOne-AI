# TakeOne AI

Production planning and production economics for AI short-drama studios. This repository is being built one phase at a time. **Phases 1–5 are implemented:** local production planning, mock generation through Temporal, attempt and cost history, immutable human reviews, retry with provider switching, production economics dashboards, structured shot specs, basic character continuity, and saved rule-based provider recommendations.

## Run locally

Requirements: Python 3.11+, Node.js 20+, npm, and Docker with its daemon running.

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
docker compose up -d db
python3 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
DATABASE_URL=postgresql+psycopg://takeone:takeone@localhost:5432/takeone .venv/bin/alembic -c apps/api/alembic.ini upgrade head
npm install
```

Start Temporal, its worker, the API, and the web app in separate terminals from the repository root:

```bash
.venv/bin/python -m takeone_api.dev_temporal
```

The first run downloads the official Temporal development server. Its local UI is at [http://localhost:8233](http://localhost:8233). Its state is stored under `.temporal/`. This server is for local development only.

```bash
.venv/bin/python -m takeone_api.worker
```

```bash
.venv/bin/uvicorn takeone_api.main:app --reload
```

```bash
npm run dev:web
```

Open [http://localhost:3000/series](http://localhost:3000/series). Create a local workspace, then a series, episode, scene, and shot. Mark the shot Ready, open it, and submit it to a mock provider. The mock returns a sample frame and **simulated** cost; it does not create a video or contact a paid provider. Open [Review](http://localhost:3000/review) to find completed attempts, then accept or reject. Rejection requires a failure reason. You can edit a rejected shot's requirements, then retry using the same or alternate mock provider. Prior attempts, costs, and decisions remain visible. The API reference is at [http://localhost:8000/docs](http://localhost:8000/docs).

Open the [Dashboard](http://localhost:3000/dashboard) for generation spend, retry waste, first-pass acceptance, and cost per accepted shot. [Analytics](http://localhost:3000/analytics) breaks those costs down by provider, model, failure reason, and episode. Both pages can be scoped to one series. The totals use generation `cost_events`; accepted and rejected counts use final `reviews`. Simulated, actual, and provisional estimated costs are labeled separately. A missing denominator shows `—` instead of a misleading zero.

On a series page, add characters and their episode-range states. On a shot page, save a structured spec with action, dialogue, selected characters, and continuity notes. The recommendation button saves a rule-based choice and simulated price; the shot form then selects that mock provider. Generation compiles a provider-specific prompt from the saved spec and current character state, and freezes both in the attempt snapshot. The recommendation is a low-confidence workflow demonstration: neither mock provider has a measured quality advantage.

The local identity is a development placeholder stored in the browser and sent as headers. It is deliberately disabled when `TAKEONE_ENV` is not `local`. Verified authentication is required before a public deployment.

## Verify

```bash
.venv/bin/pytest -q apps/api/tests
TAKEONE_TEMPORAL_TEST=1 .venv/bin/pytest -q apps/api/tests/test_temporal_integration.py
npm run typecheck --workspace @takeone/web
npm run build:web
```

The database migration can also be checked against an existing database:

```bash
.venv/bin/alembic -c apps/api/alembic.ini check
```

## Layout

- `apps/api`: FastAPI, SQLAlchemy models, Alembic migrations, and tests.
- `apps/web`: Next.js planning, continuity, recommendation, generation, review, dashboard, and analytics screens, Tailwind, and shadcn/ui style primitives.
- `docs/architecture.md`: complete MVP architecture, future schema, interfaces, workflows, cost definitions, risks, and ordered backlog.
- `docker-compose.yml`: local PostgreSQL with pgvector available for a future retrieval use case.

`apps/api/src/takeone_api/providers.py` defines the provider seam; `shot_specs.py` owns continuity, deterministic prompt compilation, and demo routing; `generation.py` owns attempt and charge rules; `review.py` owns human decisions; `analytics.py` computes ledger-backed production metrics; `workflow.py` and `worker.py` run Temporal coordination. The two mock provider configurations allow local switching, with different simulated prices. Real provider credentials and GCS media storage remain pilot work.
# content-generator
# content-generator
