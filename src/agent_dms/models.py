import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from .errors import fail

LEASE_MS = 900_000
PRESENCE_MS = 90_000
STATUS_MS = 900_000
BODY_LIMIT = 16_000
KINDS = {"message", "handoff", "question", "answer", "completion", "review", "approval"}
AVAILABILITIES = {"working", "idle", "blocked"}


def utc_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def new_id():
    return str(uuid4())


def rfc3339(ms):
    return None if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def text(value, label, maximum, *, strip=False, required=True):
    if not isinstance(value, str):
        fail("VALIDATION_ERROR", f"{label} must be text")
    result = value.strip() if strip else value
    if len(result) > maximum or (required and not result.strip()):
        fail("VALIDATION_ERROR", f"{label} must contain 1–{maximum} characters" if required else f"{label} exceeds {maximum} characters")
    return result


def no_controls(value, label):
    if any(unicodedata.category(c).startswith("C") for c in value):
        fail("VALIDATION_ERROR", f"{label} contains control or format characters")
    return value


def agent_name(value):
    return no_controls(text(unicodedata.normalize("NFC", value), "name", 64, strip=True), "name")


def status_text(value):
    if not isinstance(value, str):
        fail("VALIDATION_ERROR", "status must be text")
    result = " ".join(unicodedata.normalize("NFC", value).split())
    words = len(result.split())
    if not 1 <= words <= 30 or len(result) > 500:
        fail("VALIDATION_ERROR", "status requires 1–30 whitespace-separated words and at most 500 characters", word_count=words)
    return no_controls(result, "status"), words


def availability(value):
    if value not in AVAILABILITIES:
        fail("VALIDATION_ERROR", "availability must be working, idle or blocked")
    return value


def limit(value):
    if type(value) is not int or not 1 <= value <= 100:
        fail("VALIDATION_ERROR", "limit must be 1–100")
    return value


def key(value):
    return text(value, "idempotency_key", 200)
