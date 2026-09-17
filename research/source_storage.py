"""Content-addressed, dossier-private storage for immutable source evidence."""

import copy
import hashlib
import json

REFERENCE_KEY = "__research_source_v1__"
SOURCE_FIELDS = ("papers", "report_papers", "versions")


def compact(value, snapshots):
    if isinstance(value, list):
        return [compact(item, snapshots) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: compact(item, snapshots) for key, item in value.items()}
    if "id" in value and "title" in value:
        payload = {key: result.pop(key) for key in ("abstract", "document") if key in result}
        if payload:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(encoded.encode()).hexdigest()
            snapshots[digest] = payload
            result[REFERENCE_KEY] = digest
    return result


def references(value):
    if isinstance(value, list):
        return set().union(*(references(item) for item in value)) if value else set()
    if not isinstance(value, dict):
        return set()
    found = {value[REFERENCE_KEY]} if REFERENCE_KEY in value else set()
    for item in value.values():
        found.update(references(item))
    return found


def hydrate(value, payloads):
    if isinstance(value, list):
        return [hydrate(item, payloads) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: hydrate(item, payloads) for key, item in value.items() if key != REFERENCE_KEY}
    if REFERENCE_KEY in value:
        # A missing reference is corruption, never silently substitute incomplete evidence.
        result.update(copy.deepcopy(payloads[value[REFERENCE_KEY]]))
    return result


def load_sources(instance, value):
    from research.models import SourceSnapshot

    digests = references(value)
    if not digests:
        return value
    cache = instance.__dict__.setdefault("_source_payload_cache", {})
    missing = digests - cache.keys()
    if missing:
        cache.update(
            SourceSnapshot.objects.using(instance._state.db)
            .filter(dossier_id=instance.pk, digest__in=missing)
            .values_list("digest", "payload")
        )
    if digests - cache.keys():
        raise RuntimeError("Missing immutable source snapshot for this dossier")
    return hydrate(value, cache)
