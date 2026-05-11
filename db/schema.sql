-- Applied automatically by the Postgres Docker image on first init (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE support_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    customer_id UUID NOT NULL REFERENCES customers(id),

    title TEXT NOT NULL,
    body TEXT NOT NULL,

    duplicate_hash TEXT NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ticket_enrichments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ticket_id UUID NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,

    category TEXT,
    priority TEXT,
    sentiment TEXT,
    summary TEXT,

    status TEXT NOT NULL DEFAULT 'pending',

    model TEXT,
    prompt_version TEXT,
    error_code TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,

    is_current BOOLEAN NOT NULL DEFAULT false,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ticket_enrichments_category_check
        CHECK (category IS NULL OR category IN (
            'billing',
            'bug',
            'feature_request',
            'account',
            'other'
        )),

    CONSTRAINT ticket_enrichments_priority_check
        CHECK (priority IS NULL OR priority IN (
            'low',
            'medium',
            'high',
            'urgent'
        )),

    CONSTRAINT ticket_enrichments_sentiment_check
        CHECK (sentiment IS NULL OR sentiment IN (
            'negative',
            'neutral',
            'positive'
        )),

    CONSTRAINT ticket_enrichments_status_check
        CHECK (status IN (
            'pending',
            'processing',
            'completed',
            'failed'
        ))
);

CREATE UNIQUE INDEX one_current_enrichment_per_ticket
ON ticket_enrichments(ticket_id)
WHERE is_current = true;

CREATE INDEX idx_support_tickets_customer_id
ON support_tickets(customer_id);

CREATE INDEX idx_support_tickets_created_at
ON support_tickets(created_at DESC);

CREATE INDEX idx_ticket_enrichments_ticket_id
ON ticket_enrichments(ticket_id);

CREATE INDEX idx_ticket_enrichments_status
ON ticket_enrichments(status);

CREATE INDEX idx_ticket_enrichments_category
ON ticket_enrichments(category);

CREATE INDEX idx_ticket_enrichments_priority
ON ticket_enrichments(priority);

CREATE INDEX idx_ticket_enrichments_created_at
ON ticket_enrichments(created_at DESC);

CREATE INDEX idx_ticket_enrichments_current_filters
ON ticket_enrichments(category, priority, created_at DESC)
WHERE is_current = true;

-- Semantic search: one row per ticket (async-filled after ingest). Vector dim must match
-- OPENAI_EMBEDDING_DIMENSIONS (default 1536 for text-embedding-3-small).
CREATE TABLE ticket_search_embeddings (
    ticket_id UUID PRIMARY KEY REFERENCES support_tickets(id) ON DELETE CASCADE,

    embedding vector(1536) NOT NULL,
    model TEXT NOT NULL,
    content_hash TEXT NOT NULL,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ticket_search_embeddings_hnsw
ON ticket_search_embeddings
USING hnsw (embedding vector_cosine_ops);
