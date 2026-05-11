"""Single-shot LLM enrichment via OpenAI (JSON schema enforced in prompt)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

from annotator_backend.config import Settings

PROMPT_VERSION = "1"

ALLOWED_CATEGORY = frozenset(
    {"billing", "bug", "feature_request", "account", "other"},
)
ALLOWED_PRIORITY = frozenset({"low", "medium", "high", "urgent"})
ALLOWED_SENTIMENT = frozenset({"negative", "neutral", "positive"})


@dataclass(frozen=True)
class EnrichmentResult:
    category: str
    priority: str
    sentiment: str
    summary: str


class EnrichmentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def build_system_prompt() -> str:
    return """You are triaging support tickets for BuildIt, a B2B SaaS company.

Task: From the ticket title and body, output a single JSON object with exactly these keys:
- "category": one of billing, bug, feature_request, account, other
- "priority": one of low, medium, high, urgent
- "sentiment": one of negative, neutral, positive
- "summary": one English sentence, at most 20 words, describing the issue generically

Rules for PII and secrets:
- Do not include email addresses, names, phone numbers, account identifiers, payment or card \
details, passwords, API keys, tokens, or any personally identifying information in "summary" \
or in any field.
- Use generic phrasing (e.g. "customer reports a duplicate subscription charge" rather than \
quoting names, emails, or card data).

Example 1:
Input title: Charged twice for October subscription
Input body: Hi, I see two charges of €49 on my card from Oct 3. Please refund one. \
This is the second time this happens and I'm getting frustrated.
Output JSON:
{"category":"billing","priority":"high","sentiment":"negative","summary":"Customer reports \
duplicate subscription charges and frustration while asking for a refund."}

Example 2:
Input title: Love the new dashboard
Input body: Just wanted to say the redesign is great. Much cleaner. Would be amazing to have \
dark mode though — my eyes will thank you.
Output JSON:
{"category":"feature_request","priority":"low","sentiment":"positive","summary":"Customer \
praises the dashboard redesign and requests a future dark mode option."}

Return only valid JSON, with no markdown fences and no extra keys.
"""


def _user_message(title: str, body: str) -> str:
    return f"title: {title}\n\nbody: {body}"


def _parse_payload(text: str) -> EnrichmentResult:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise EnrichmentError("invalid_json", f"LLM returned non-JSON: {e}") from e
    if not isinstance(data, dict):
        raise EnrichmentError("invalid_shape", "LLM JSON root must be an object")
    try:
        category = data["category"]
        priority = data["priority"]
        sentiment = data["sentiment"]
        summary = data["summary"]
    except KeyError as e:
        raise EnrichmentError("missing_keys", f"Missing key in LLM JSON: {e}") from e
    for key, value in (("category", category), ("priority", priority), ("sentiment", sentiment)):
        if not isinstance(value, str):
            raise EnrichmentError("invalid_types", f"{key} must be a string")
    if not isinstance(summary, str):
        raise EnrichmentError("invalid_types", "summary must be a string")
    if category not in ALLOWED_CATEGORY:
        raise EnrichmentError("invalid_category", category)
    if priority not in ALLOWED_PRIORITY:
        raise EnrichmentError("invalid_priority", priority)
    if sentiment not in ALLOWED_SENTIMENT:
        raise EnrichmentError("invalid_sentiment", sentiment)
    word_count = len(summary.split())
    if word_count > 25:
        raise EnrichmentError("summary_too_long", f"summary has {word_count} words (max 25)")
    return EnrichmentResult(
        category=category,
        priority=priority,
        sentiment=sentiment,
        summary=summary.strip(),
    )


def enrich_ticket(*, title: str, body: str, settings: Settings) -> EnrichmentResult:
    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": _user_message(title, body)},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise EnrichmentError("provider_error", str(e)) from e
    choice = completion.choices[0].message.content
    if not choice:
        raise EnrichmentError("empty_completion", "LLM returned empty content")
    return _parse_payload(choice)
