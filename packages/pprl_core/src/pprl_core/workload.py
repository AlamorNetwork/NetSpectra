"""Versioned synthetic bytes generated with SHA256 rather than runtime RNG state."""

import hashlib


def seeded_payload(seed: int, index: int) -> bytes:
    """Return 32–512 reproducible bytes; this is not a cryptographic protocol."""
    if type(seed) is not int or not 0 <= seed <= 4294967295:
        raise ValueError("invalid seed")
    if type(index) is not int or not 0 <= index < 10:
        raise ValueError("invalid repetition index")
    prefix = f"pprl-sha256-v1:{seed}:{index}:".encode("ascii")
    size = 32 + int.from_bytes(hashlib.sha256(prefix).digest()[:2], "big") % 481
    blocks = [
        hashlib.sha256(prefix + str(i).encode("ascii")).digest()
        for i in range((size + 31) // 32)
    ]
    return b"".join(blocks)[:size]


def workload_plan(payloads: list[bytes], protocol: str, generator: str) -> dict:
    """A stable comparison target excluding process IDs, ports and wall clock."""
    return {
        "generator": generator,
        "protocol": protocol,
        "samples": [
            {
                "index": i,
                "size_bytes": len(payload),
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
            }
            for i, payload in enumerate(payloads)
        ],
    }
