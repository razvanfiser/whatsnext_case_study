# BuildIt support ticket triage API

Python/FastAPI service that ingests support tickets, enriches them asynchronously with a structured LLM call (category, priority, sentiment, short summary), stores them in PostgreSQL (**with pgvector** for optional semantic search), and supports listing with filters.

- **Async enrichment:** `POST /tickets` does not wait for the LLM; clients use **`GET /tickets/{id}`** until `enrichment_status` is `completed` or `failed`. While this differs from a strictly synchronous reading of the take-home brief, it matches the latency trade-off discussed in the problem statement.
- **Semantic search:** Embeddings are stored in **`ticket_search_embeddings`** (pgvector, FK to `support_tickets`). Ingest is **async** like enrichment; search only returns tickets already indexed.
- **BackgroundTasks:** Enrichment runs **in the same process** after the response is sent. If the API process restarts before the job finishes, a row can stay `pending` or `processing` until a future sweeper/queue (not implemented here).
- **LLM retries:** Transient provider errors (timeouts, connection issues, HTTP 429, HTTP 5xx) are retried up to **3** times with exponential backoff (`1s`, `2s`). Non-retryable failures (invalid JSON, validation) mark the enrichment `failed` immediately. `retry_count` and `last_attempt_at` are updated on attempts.
- **Duplicates:** `duplicate_hash` is unique; content-hash duplicates return **200** without a second LLM job.
- **PII / LLM boundary:** Stored ticket `title`/`body` (and API responses) are **unchanged**. Before each enrichment call, a **best-effort regex pass** ([`annotator_backend/pii_redact.py`](annotator_backend/pii_redact.py)) replaces obvious high-risk spans in the copy sent to the provider with fixed tokens (`[REDACTED_SSN]`, `[REDACTED_PHONE]`, `[REDACTED_CREDIT_CARD]`, `[REDACTED_API_KEY]`). **Email addresses are not redacted** (triage context). This is not a compliance-grade DLP layer and can miss real PII or false-positive on long numeric strings.
- **PII:** Ticket `title`/`body` (after that redaction step) go to the LLM; `customer_email` is only in the JSON body and is not injected into that user message. The prompt instructs the model not to echo PII in structured fields; raw LLM responses are not stored—only parsed metadata.
- **Logging:** Stdlib `logging` configured at startup ([`annotator_backend/logging_config.py`](annotator_backend/logging_config.py)); when **`LOG_JSON`** is true (default), each line to stdout is one JSON object (`python-json-logger`) with stable keys (`event`, IDs, attempts, outcomes, embedding-index fields). Set **`LOG_JSON=false`** for human-readable plain text locally. Same privacy rules apply: **no** ticket bodies, prompts, summaries, or raw LLM output (see [notes.md](notes.md)).

## Requirements

- Python 3.11+
- Docker and Docker Compose (optional but recommended)
- An OpenAI API key

## Environment variables

Copy [`.env.example`](.env.example) to `.env` and set your secrets. Important keys:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API key for chat completions |
| `OPENAI_MODEL` | Model name (default `gpt-4o-mini`) |
| `LLM_TIMEOUT_SECONDS` | Per-request timeout for the OpenAI client |
| `OPENAI_EMBEDDING_MODEL` | Embedding model for `POST /tickets/search` (default `text-embedding-3-small`) |
| `OPENAI_EMBEDDING_DIMENSIONS` | Vector size; must match `vector(N)` in [`db/schema.sql`](db/schema.sql) (default `1536`) |
| `POSTGRES_*` | Credentials for the Postgres container |
| `DATABASE_URL` | SQLAlchemy URL; use host `db` from Compose, `localhost` when running the API on the host |
| `LOG_JSON` | If `true` (default), root/app logs are JSON lines; set `false` for plain-text formatter |

## Run with Docker Compose

From the repo root:

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`. Postgres listens on `localhost:5432` as well.

Note: the database schema runs only on **first** creation of the Postgres data volume. The Compose image includes **pgvector**. To reset the DB (drops data), run `docker compose down -v` then `docker compose up` again. If you reuse an old volume from before pgvector, either reset as above or apply `CREATE EXTENSION vector` and the `ticket_search_embeddings` DDL from [`db/schema.sql`](db/schema.sql) manually.

## Run locally (without Docker for the app)

1. Start Postgres (e.g. use Compose with only the `db` service, or a local instance matching [`db/schema.sql`](db/schema.sql)).
2. Create a virtualenv and install dependencies:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Set `DATABASE_URL` in `.env` (e.g. `postgresql+psycopg://USER:PASS@localhost:5432/DBNAME`).
4. Run the API:

   ```bash
   uvicorn annotator_backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

## API overview

- `POST /tickets` — body: `title`, `body`, `customer_email`. Persists the ticket and a **pending** enrichment row, returns **201** immediately (enrichment fields empty / status `pending`). A **background task** then calls the LLM and updates that row to `processing` → `completed` or `failed`. Another task indexes **title+body** for semantic search (embeddings in `ticket_search_embeddings`). **Poll** `GET /tickets/{id}` for final category, priority, sentiment, and summary. Duplicate submissions (same normalized email/title/body / `duplicate_hash`) return **200** with the existing record and do not enqueue another enrichment or re-index.
- `POST /tickets/search` — body: `{ "query": "plain language search", "limit": 10 }` (optional `limit`, max 50). Embeds the query with the same model as ingest, runs **cosine distance** against indexed tickets, returns ranked [`TicketOut`](annotator_backend/schemas.py)-shaped hits plus `distance` (lower is closer). Only tickets that have been indexed appear; **poll** after `POST /tickets` if the embedding job is still running. **502** if the embedding provider fails.
- `GET /tickets` — optional query params: `enrichment_status` (`pending`, `processing`, `completed`, `failed`), `category`, `priority`, `since` (ISO-8601), `limit`, `offset`.
- `GET /tickets/{id}` — single ticket with current enrichment.

OpenAPI docs: `http://localhost:8000/docs` when the server is running.

## Linting and formatting

```bash
ruff check annotator_backend db
ruff format annotator_backend db
```

## Tests

```bash
python3 -m unittest discover -s annotator_backend/tests -p 'test_*.py' -v
```

## Demo / seed data

Four sample tickets from the case brief (with **completed** enrichments) can be loaded for manual testing:

```bash
# Rows only (tickets + enrichments). Safe to re-run; skips when duplicate_hash exists.
python3 -m annotator_backend.seed_demo

# Also call OpenAI and fill ticket_search_embeddings (needs OPENAI_API_KEY, pgvector schema).
python3 -m annotator_backend.seed_demo --embeddings
```

Use the same `DATABASE_URL` / `.env` as the app. Re-run with `--embeddings` to backfill vectors after transient failures. If you already created a ticket via `POST /tickets` with identical title/body/email, the seed **skips** that row (same `duplicate_hash`).
