from __future__ import annotations

import base64
import gzip
import json
from typing import Any


ENCODING_GZIP_BASE64 = "gzip+base64"


def encode_payload(
    payload: dict[str, Any],
    threshold_bytes: int = 64 * 1024,
) -> dict[str, Any]:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    if len(raw) < threshold_bytes:
        return payload

    compressed = gzip.compress(raw, compresslevel=6)
    return {
        "_encoded": True,
        "encoding": ENCODING_GZIP_BASE64,
        "original_bytes": len(raw),
        "compressed_bytes": len(compressed),
        "data": base64.b64encode(compressed).decode("ascii"),
    }


def decode_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not payload.get("_encoded"):
        return payload

    encoding = payload.get("encoding")
    if encoding != ENCODING_GZIP_BASE64:
        raise ValueError(
            f"Неподдерживаемое кодирование ответа: {encoding}"
        )

    encoded = str(payload.get("data") or "")
    compressed = base64.b64decode(encoded)
    raw = gzip.decompress(compressed)
    result = json.loads(raw.decode("utf-8"))

    if not isinstance(result, dict):
        raise ValueError("Декодированный ответ должен быть объектом")
    return result
