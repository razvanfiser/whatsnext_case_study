# Technical Case — Support Ticket Triage API

**Time budget:** ~1.5–2 hours (with AI assistance, we expect you to use Claude Code, Cursor, Codex, or similar)
**Deliverable:** a link to a public GitHub repo

---

## The brief

You're building the first version of a backend service for **BuildIt**, a fictional SaaS company. Customers submit support tickets through a web form. Today those tickets land in a shared inbox and are triaged manually.

Your job: build an API that ingests tickets, uses an LLM to enrich them with structured metadata, stores them in a database, and lets the support team query them.

## What we want to see

You pick the stack (within the constraints below)

### Must-have

1. **`POST /tickets`** — accepts a ticket (`title`, `body`, `customer_email`), enriches it with an LLM, stores it, returns the enriched record.
   - LLM enrichment must produce:
     - `category`: one of `billing`, `bug`, `feature_request`, `account`, `other`
     - `priority`: one of `low`, `medium`, `high`, `urgent`
     - `sentiment`: one of `negative`, `neutral`, `positive`
     - `summary`: one sentence, max ~20 words

2. **`GET /tickets`** — list tickets with filters: `category`, `priority`, `since` (ISO date), pagination.

3. **`GET /tickets/{id}`** — fetch a single ticket.

4. **A relational database** (Postgres preferred) with a schema you've designed intentionally. We care about your choices here.

5. **Docker + `docker-compose.yml`** — `docker compose up` should start the app and the database. The only thing we should need to do is set an LLM API key.

6. **Python backend.** FastAPI/Litestar/Flask/Django — your call.

7. **Linting + formatting configured** (ruff is fine). Running `ruff check` should pass on your repo.

8. **Clear `README.md`** explaining: what it does, how to run it locally, how to run it in Docker, env vars needed, and any decisions you want to call out.

9. **`.env.example`** with documented variables. No secrets in the repo.

### Nice-to-have (only if time allows, do NOT sacrifice the above)

- `POST /tickets/search` — semantic search over ticket bodies using embeddings (pgvector, Chroma, sqlite-vec — your call).
- A handful of tests (even 2–3 well-chosen ones).
- Pre-commit hook.
- Structured logging.

### Constraints

- **Language:** Python.
- **LLM provider:** Anthropic, OpenAI, or any provider you prefer
- **Package manager:** your call, but we use `uv` internally.
- **No frontend needed.** The API is the deliverable.

## Design considerations

These aren't separate requirements. You don't need to fully solve all of them in 2 hours. Pick what you'll address, note what you won't, and be ready to talk about the trade-offs you made.

- **LLM latency and reliability.** Our LLM provider has p99 response times around 8–10 seconds and occasional multi-minute degradations. What does a user submitting a ticket experience during a slow response? During an outage? How long is it acceptable for your API to hang before it gives up, and what does it do then?

- **Sensitive data.** Support tickets contain personal data (names, email addresses, sometimes phone numbers). Occasionally customers share things they shouldn’t (API keys pasted into a bug report, payment details in a refund request, a screenshot with a surname visible). What does your system do with that content on the way to the LLM, in the database, and in your logs?

- **Duplicate submissions.** Customers double-click submit. Support widgets retry on network timeouts. A ticket submitted twice shouldn't become two rows in your database and two calls to the LLM, but your definition of "duplicate" is a design decision. What's yours?

We will ask about each of these in the follow-up. *"I thought about X and deliberately chose Y because Z"* is a great answer. *"I deferred this to focus on the core flow because W"* is also fine if you can defend it. *"I didn't notice this was a concern"* is not.

## Sample test data

Use these to exercise your API. Feel free to generate more.

```json
{
  "title": "Charged twice for October subscription",
  "body": "Hi, I see two charges of €49 on my card from Oct 3. Please refund one. This is the second time this happens and I'm getting frustrated.",
  "customer_email": "anna@example.com"
}
```

```json
{
  "title": "App crashes on PDF export",
  "body": "Every time I try to export my project to PDF the app freezes completely and I lose unsaved work. I'm on v2.3.1, macOS 14.2. Happens 100% of the time with files over ~20 pages.",
  "customer_email": "dev@startup.io"
}
```

```json
{
  "title": "Love the new dashboard",
  "body": "Just wanted to say the redesign is great. Much cleaner. Would be amazing to have dark mode though — my eyes will thank you.",
  "customer_email": "happy@customer.com"
}
```

```json
{
  "title": "Can't log in",
  "body": "Password reset email never arrives. Checked spam. Tried three times over the last hour. My account email is below.",
  "customer_email": "locked.out@example.org"
}
```

## How we'll evaluate

We'll clone your repo, read the code, run `docker compose up`, and hit the API. Then we'll have a 30-minute conversation with you where we'll ask you to walk us through:

- The prompt you wrote and what could break it
- Your database schema and why
- Where you used AI and where you wrote code yourself
- The design considerations above 
- What you'd do next if you had another day
- What happens when the LLM provider is down, slow, or returns garbage


## Submission

- A link to a public GitHub repo
- Total time spent (rough estimate is fine)
- Anything you want us to know before we look at it