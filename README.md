# two-way-sync

A FastAPI service that synchronises invoices between an internal invoicing system (`ideaas`) and QuickBooks Online. Outbound (local → QBO) writes go through a `sync_jobs` queue. Inbound (QBO → local) webhooks land in a `webhook_events` queue. A single async worker drains both queues with exponential backoff and Postgres row-level locking. All cross-system writes are audited in append-only tables enforced by database triggers.

For architecture, data model, sequence diagrams, idempotency strategy, edge-case coverage, and the full list of implicit assumptions, see [`DESIGN.md`](DESIGN.md).

---

## Assumptions

The following assumptions are baked into the design. Each one narrows scope deliberately; the "if I had time" rationale for each is in [`DESIGN.md`](DESIGN.md).

**Voided invoices are immutable.** A voided invoice cannot be updated. QBO preserves the invoice number and zeroes the balance as a permanent financial record. Allowing edits after voiding would corrupt the audit trail and break double-entry accounting invariants.

**CustomerRef values already exist in QBO.** Every `customer_id` on a local invoice maps to a customer that has already been created in QBO. Syncing customers requires its own create-before-reference workflow against the QBO `/customer` endpoint; that is out of scope. The seed script pre-creates matching `external_id` values (`1` and `24`) so the mock round-trips without errors.

**ItemRef values already exist in QBO.** Every line-item `item_id` sent to QBO must correspond to an item already present in QBO's Items list. Creating missing items would require a separate `/items` sync pass before pushing an invoice; that is out of scope.

**Access tokens are permanent.** `Company.access_token` is read once per request and used as a bearer token without expiry checks. Real Intuit tokens expire after one hour and require an OAuth 2.0 refresh flow (authorization code grant, token rotation, concurrent-refresh locking). Implementing that workflow is out of scope; the Mockoon mock accepts any bearer value.

**The system is designed to support multiple invoice providers.** The `providers` table (seeded with `QuickBooks` and `Xero`) is foreign-keyed from `companies` so a future provider (Zoho, FreshBooks, etc.) can be added without a schema migration. Provider-specific dispatch logic is not yet factored out.

**QBO fires a webhook back on every write we push.** When the outbound worker successfully creates, updates, voids, or deletes an invoice in QBO, QBO sends a corresponding event back to our webhook endpoint. The inbound idempotency gate (SyncToken guard for `created`/`updated`, status-mirror checks for `voided`/`deleted`) exists specifically to absorb these echoes without producing duplicate history rows or token regressions.

**The webhook payload follows the CloudEvents envelope.** Inbound events are expected in this shape:

```json
[
  {
    "specversion": "1.0",
    "id": "88cd52aa-33b6-4351-9aa4-47572edbd068",
    "source": "intuit.dsnBgbseACLLRZNxo2dfc4evmEJdxde58xeeYcZliOU=",
    "type": "qbo.invoice.created.v1",
    "datacontenttype": "application/json",
    "time": "2025-09-10T21:31:25.179851517Z",
    "intuitentityid": "1234",
    "intuitaccountid": "310687",
    "data": {}
  }
]
```

`intuitentityid` is the QBO Invoice `Id`; `intuitaccountid` is the QBO `realmId` used to route the event to the correct company.

**`Preferences:CustomTxnNumber` is `true` in QBO.** This preference lets the system control the `DocNumber` field on every invoice, which is set to the local `invoice_number` (e.g. `INV-2026-000000001`). Without it QBO auto-assigns its own DocNumber, which breaks the DocNumber-based reconciliation used on outbound create retries (edge case #5 in `DESIGN.md`).

**Webhook signature verification is assumed but not implemented in this environment.** In production, the `intuit-signature` header would be verified per-company using `hmac.compare_digest` against a QBO-issued webhook verifier token. That token requires a live Intuit developer account to obtain; the Mockoon simulate routes carry no signature. The endpoint currently trusts any POST to `/webhooks/quickbooks`.

**One company maps to exactly one QBO realm.** `Company.external_id` holds the realm and is the only routing key used by the inbound handler. Multi-realm companies (a single tenant with several QBO files) would need a join table and a richer routing layer, and are out of scope.

**QBO `SyncToken` is monotonic and numeric.** The inbound out-of-order gate compares tokens as integers, so the contract assumes QBO never resets, recycles, or returns non-numeric tokens for an invoice. Non-numeric tokens are logged and the event is skipped rather than crashing the worker, but a real token reset (e.g. on a company data restore) would let echoes leak through the gate.

---

## Prerequisites

- macOS or Linux
- [`uv`](https://docs.astral.sh/uv/) `>= 0.4` (Python toolchain and dependency manager). On macOS: `brew install uv`.
- [Docker](https://www.docker.com/) `>= 20.10` with the `docker compose` plugin (Postgres container).
- [Node.js](https://nodejs.org/) `>= 20` (Mockoon CLI for the QBO mock). On macOS: `brew install node`.
- [`mise`](https://mise.jdx.dev/) (optional) pins `node 24.15` and `uv 0.11.11` via `mise.toml`. If you have it: `brew install mise && mise install`.

`uv` will provision the Python `3.13` interpreter declared in `.python-version` automatically on first `uv sync`.

---

## Quickstart

Run these commands in order from the repository root. Each step is idempotent.

### 1. Install Python dependencies

```bash
uv sync
```

This creates `.venv/`, installs the locked dependencies from `uv.lock`, and provisions Python 3.13.

`pyproject.toml` pins the package index to public PyPI under `[tool.uv]`. This project-level config wins over any user-level `~/.config/uv/uv.toml`  so `uv sync` is reproducible on a clean machine without altering global settings.

#### Regenerating `uv.lock` from public PyPI

If you ever need to rebuild the lockfile (for example after editing `pyproject.toml`) and your machine has a private index configured globally, run:

```bash
uv lock --refresh --default-index https://pypi.org/simple/
```

The `--default-index` flag overrides any default index inherited from a user-level `uv.toml`. No environment variable export and no edits to `~/.config/uv/uv.toml` are required.

### 2. Install Node dependencies

```bash
npm install
```

Installs `@mockoon/cli` locally for the QBO mock server.

### 3. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env` so it matches the values below. The defaults assume the local Docker Postgres and the local Mockoon mock from this repo.

```dotenv
DATABASE_URL=postgresql://development:test123@localhost:5432/ideaas
QUICKBOOKS_BASE_URL=http://localhost:4000
WORKER_POLL_INTERVAL=15
```

`DATABASE_URL` is required; `app/db/session.py` raises `ValueError` at import time if it is unset. `QUICKBOOKS_BASE_URL` defaults to `http://localhost:4000` and `WORKER_POLL_INTERVAL` defaults to `15` seconds when omitted.

### 4. Start Postgres

```bash
docker compose up -d
```

Brings up `postgres:13-alpine` on `localhost:5432` with the credentials baked into `docker-compose.yml` (`development:test123`, database `ideaas`). Wait two or three seconds for the container to accept connections.

### 5. Apply migrations

```bash
uv run alembic upgrade head
```

There are 10 migrations covering the initial schema, append-only triggers on `api_logs` and `invoice_history`, the `sync_jobs` and `webhook_events` queues, and the `origin` / `sync_status` columns on `invoices`.

### 6. Seed reference data

```bash
uv run python -m scripts.seed
```

Inserts 2 providers (`QuickBooks`, `Xero`), 2 users (Faker-generated), 2 companies (`Waste Management` realm `111222333`, `Republic Services` realm `444555666`), and 2 customers (`Amy's Bird Sanctuary` external_id `1`, `Sonnenschein Family Store` external_id `24`). The script logs nothing on success; verify by querying:

```bash
docker exec -it two-way-sync-postgres-1 \
  psql -U development -d ideaas -c "SELECT id, company_name, external_id FROM companies;"
```

### 7. Start the QBO mock

In a separate terminal:

```bash
npm run mock
```

Serves the Mockoon environment defined in `quickbooks-mock.json` on `http://localhost:4000`. It exposes:

- `POST /v3/company/:companyId/invoice` (create / update / delete / void, dispatched by `?operation=` query param and request body fields)
- `GET /v3/company/:companyId/invoice/:invoiceId` (sequential responses: `SyncToken=0` then `SyncToken=1` then it cycles)
- `GET /v3/company/:companyId/query` (returns an empty result by default; returns a pre-existing invoice `Id=999`, `SyncToken=0` when the query string contains `DocNumber=INV-2026-RECONCILE-001`, used to drive the outbound-create reconciliation path on retry)
- Four `POST /simulate/qbo/invoice/{created|updated|deleted|voided}` routes that fire a Mockoon callback to `http://localhost:8000/webhooks/quickbooks` so you can drive the inbound flow without a real Intuit webhook.

### 8. Start the application

In another terminal:

```bash
uv run fastapi dev
```

Serves the API on `http://localhost:8000` and starts the async `sync_worker` in the same process via the FastAPI `lifespan` hook. Confirm:

```bash
curl -s http://localhost:8000/health
# {"status":"online","database":"connected"}
```

OpenAPI docs: `http://localhost:8000/docs`.

---

## Smoke test (end-to-end)

For a single-command sanity check, use the snippets below. For a guided tour that exercises every edge case the system handles (webhook deduplication, race conditions, out-of-order updates, outbound reconciliation, audit immutability, etc.), see [`DEMO.md`](./DEMO.md).

With Postgres, Mockoon, and the app running:

### Outbound: create a local invoice and watch it sync to QBO

```bash
curl -s -X POST http://localhost:8000/invoices \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": 1,
    "customer_id": 1,
    "total_amount": "500.00",
    "issue_date": "2026-05-13",
    "due_date": "2026-06-13",
    "items": [
      {"item_id": "1", "description": "Consulting", "quantity": "1", "unit_price": "500.00", "amount": "500.00"}
    ]
  }'
```

Within `WORKER_POLL_INTERVAL` seconds the worker picks up the `sync_jobs` row, calls the mock, and updates the invoice. Verify:

```bash
docker exec two-way-sync-postgres-1 \
  psql -U development -d ideaas -c \
  "SELECT id, external_invoice_id, status, sync_status, sync_token FROM invoices;"
```

You should see `external_invoice_id=238`, `status=Open`, `sync_status=complete`, `sync_token=0`.

### Inbound: trigger a simulated QBO webhook

```bash
curl -s -X POST http://localhost:4000/simulate/qbo/invoice/created
```

The mock fires its callback to `POST /webhooks/quickbooks`. The endpoint enqueues a `webhook_events` row; the worker reads the full invoice from the mock and persists a new local invoice with `origin='qbo'`. Verify:

```bash
docker exec two-way-sync-postgres-1 \
  psql -U development -d ideaas -c \
  "SELECT id, external_invoice_id, status, sync_status, origin FROM invoices;"
```

A second invoice with `external_invoice_id=9001` and `origin='qbo'` will appear.

### Idempotency: replay the same webhook

```bash
curl -s -X POST http://localhost:8000/webhooks/quickbooks \
  -H "Content-Type: application/json" \
  -d '[{"id":"sim-evt-created-001","type":"qbo.invoice.created.v1","intuitentityid":"9001","intuitaccountid":"111222333","data":{}}]'

docker exec two-way-sync-postgres-1 \
  psql -U development -d ideaas -c \
  "SELECT count(*) FROM webhook_events WHERE cloudevent_id='sim-evt-created-001';"
```

Count remains `1`. The endpoint dedups by `cloudevent_id`.

---

## Tests

```bash
uv run pytest -q
```

75 tests cover the four service-layer operations (create / update / delete / void), the inbound webhook handler for each event type including stale-token, non-numeric-token, and already-applied skips, the outbound executor for each operation including the `external_invoice_id`-already-set short-circuit, DocNumber-based reconciliation on create retries, and the SyncToken-conflict path that flips an invoice to `sync_status='conflict'` when QBO state diverges from intent. The async `sync_worker` is exercised for exponential-backoff retries, `ConflictError` short-circuiting, and the `max_attempts` terminal path. The `POST /webhooks/quickbooks` HTTP endpoint is covered for dedup (including the `IntegrityError` race), unknown-realm drops, missing fields, and unrecognised event types. Tests use `MagicMock` databases; they do not require Docker or Postgres.

---

## Lint and format

```bash
uv run ruff check .
uv run ruff format --check .
```

Migrations under `alembic/versions/` are excluded from `ruff` per `pyproject.toml`.

---

## Project layout

```
alembic/                  Alembic config and migrations (10 revisions)
app/
  api/                    FastAPI routers (invoices, webhooks)
  core/                   config, structured logging, audit helpers
  db/                     SQLAlchemy engine, session, declarative base
  integrations/           QuickBooksClient (requests-based)
  models/                 SQLAlchemy ORM models
  schemas/                Pydantic request and response models
  services/               invoice_service, webhook_handler, sync_executor
  workers/                sync_worker async loop
  main.py                 FastAPI app and lifespan
scripts/seed.py           reference-data seeder
tests/                    pytest suite (mocked DB)
quickbooks-mock.json      Mockoon environment for the QBO API
quickbooks_api.md         QBO Invoice API reference
docker-compose.yml        Postgres 13
.env.example              environment template
```

---

## Operational commands reference

| Command | Purpose |
|---|---|
| `docker compose up -d` | Start Postgres in the background |
| `docker compose down` | Stop and remove the Postgres container |
| `docker compose down -v` | Same plus delete the database volume (destructive) |
| `uv run alembic upgrade head` | Apply all pending migrations |
| `uv run alembic downgrade -1` | Roll back the most recent migration |
| `uv run alembic revision --autogenerate -m "msg"` | Generate a new migration from model changes |
| `uv run python -m scripts.seed` | Seed providers, users, companies, customers |
| `npm run mock` | Start Mockoon QBO mock on port 4000 |
| `npm run mock:status` | Show Mockoon process info |
| `npm run mock:kill` | Stop Mockoon |
| `uv run fastapi dev` | Run the app + async worker in dev mode |
| `uv run fastapi run` | Run the app in production mode |
| `uv run pytest -q` | Run the test suite |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ValueError: DATABASE_URL environment variable is not set` at startup | `.env` is missing or `DATABASE_URL` is empty. | Recreate `.env` from `.env.example` with the value in step 3 above. |
| `psycopg2.OperationalError: connection refused` | Postgres is not running yet. | `docker compose up -d`, wait ~3 seconds. |
| Webhook simulation returns 200 but no invoice appears | The Mockoon callback target points to `http://localhost:8000/webhooks/quickbooks`. The app must be reachable on that exact URL. | Run `uv run fastapi dev` (binds `127.0.0.1:8000` by default). |
| `ck_invoice_number_min_length` constraint error | An invoice was inserted without going through the SQLAlchemy ORM (the `after_insert` event sets the `invoice_number`). | Use the API or the ORM; do not bulk-INSERT through raw SQL. |
| Worker never picks up jobs | `WORKER_POLL_INTERVAL` is high or the worker task crashed. | Check the FastAPI process logs; lower the interval in `.env`. |
| `requests.exceptions.HTTPError` on outbound update | The mock returned a 4xx because the request did not match a Mockoon rule. | Confirm `DocNumber` and `sparse: true` flags match `quickbooks-mock.json`. |
| `uv sync` fails with `failed to resolve` or hash mismatches against your private registry | A user-level `uv.toml` is overriding the project index. | The project pins public PyPI under `[tool.uv]` in `pyproject.toml`; this should win. If it does not, regenerate the lockfile with `uv lock --refresh --default-index https://pypi.org/simple/`. |
