"""Shared, deterministic grounding checks used by both CVTailoringService and
GroundingReviewerService.

These are structural, regex/keyword-based checks - not an LLM's self-report -
specifically because "did this text invent a metric/technology" is something
a whitelist/pattern check can verify far more reliably than asking a model
to grade its own work.
"""

from __future__ import annotations

import re

KNOWN_TECH_KEYWORDS = {
    "aws", "gcp", "azure", "kubernetes", "docker", "terraform", "react", "vue", "angular",
    "python", "java", "javascript", "typescript", "sql", "postgres", "postgresql", "mysql",
    "mongodb", "redis", "kafka", "spark", "hadoop", "airflow", "tensorflow", "pytorch",
    "fastapi", "django", "flask", "node", "nodejs", "graphql", "grpc", "jenkins",
    "gitlab", "github", "microservices", "lambda", "dynamodb",
    "elasticsearch", "rabbitmq", "sqlalchemy", "pandas", "numpy", "scikit-learn", "sklearn",
    "anthropic", "openai", "pgvector", "alembic", "pydantic", "next.js", "nextjs",
}  # fmt: skip

_NUMBER_RE = re.compile(r"\b\d[\d,.]*%?\b")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*")


def _lower_tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def find_invented_metrics(generated_text: str, grounded_text: str) -> list[str]:
    """Numbers/percentages present in generated_text but not anywhere in
    the grounded (original/evidence/research) text - a strong invented-
    metric signal, since real numbers should trace back to something the
    model was actually given."""
    generated_numbers = set(_NUMBER_RE.findall(generated_text))
    grounded_numbers = set(_NUMBER_RE.findall(grounded_text))
    return sorted(generated_numbers - grounded_numbers)


def find_invented_technologies(generated_text: str, grounded_text: str) -> list[str]:
    """Known technology keywords mentioned in generated_text that don't
    appear anywhere in the grounded text - flags a plausible invented/
    unsupported technology claim."""
    generated_tokens = _lower_tokens(generated_text) & KNOWN_TECH_KEYWORDS
    grounded_tokens = _lower_tokens(grounded_text)
    return sorted(generated_tokens - grounded_tokens)
