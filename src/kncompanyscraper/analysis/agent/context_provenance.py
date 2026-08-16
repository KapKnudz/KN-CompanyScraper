from dataclasses import asdict
from hashlib import sha256
import json


def deterministic_context_sha256(candidate) -> str:
    payload = json.dumps(
        asdict(candidate)["full_results"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()
