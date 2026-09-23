"""Deterministic fingerprint-based sampling.

Sampling decisions are reproducible: the same interaction fingerprint
at the same sample_rate always produces the same decision.
"""

from __future__ import annotations

import hashlib


def should_sample(fingerprint: str, sample_rate: float) -> bool:
    """Deterministically decide whether to sample based on fingerprint hash.

    Args:
        fingerprint: A stable hash string identifying the interaction.
        sample_rate: Float in [0.0, 1.0]. 1.0 = always, 0.0 = never.

    Returns:
        True if the interaction should be captured.
    """
    if sample_rate >= 1.0:
        return True
    if sample_rate <= 0.0:
        return False
    hash_val = int(hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:8], 16)
    threshold = hash_val / 0xFFFFFFFF
    return threshold < sample_rate
