"""A daily cap on LLM calls, shared by the web server and the Celery worker (via the cache).

When the cap is reached, callers raise -> the existing fallbacks take over:
triage uses the rule-based classifier, first-aid returns the guide text directly.
So the app keeps working; it just stops spending Groq tokens until midnight UTC.
"""
import datetime
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class LLMBudgetExceeded(RuntimeError):
    pass


def _key():
    return f"llm-calls:{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d}"


def spend_llm_call(purpose: str):
    """Count one LLM call. Raises LLMBudgetExceeded if today's limit is used up."""
    limit = settings.LLM_DAILY_CALL_LIMIT
    if limit <= 0:  # 0 = unlimited
        return
    key = _key()
    cache.add(key, 0, timeout=60 * 60 * 25)  # create today's counter if missing
    used = cache.incr(key)
    if used > limit:
        logger.warning("LLM daily budget reached (%s/%s), skipping %s", used, limit, purpose)
        raise LLMBudgetExceeded(f"daily LLM budget of {limit} calls reached")


def calls_used_today() -> int:
    return cache.get(_key(), 0)
