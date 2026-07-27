"""Compact influence functions for intersection-driven displacement data."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class WeightingFunction:
    """Protocol-like base class for normalized distance weights."""

    def __call__(self, normalized_distance):
        raise NotImplementedError


@dataclass(frozen=True)
class InverseDistanceWeighting(WeightingFunction):
    """Compact inverse-distance weight.

    The usual singular IDW expression is multiplied by a compact smoothstep
    envelope and normalized to one at the source.  Consequently the returned
    value is one at zero distance and exactly zero at and beyond unit distance.
    """

    exponent: float = 2.0
    epsilon: float = 1e-12

    def __call__(self, normalized_distance):
        distance = np.asarray(normalized_distance, dtype=float)
        clipped = np.clip(distance, 0.0, 1.0)
        envelope = 1.0 - clipped * clipped * (3.0 - 2.0 * clipped)
        inverse = (1.0 / (1.0 + clipped)) ** float(self.exponent)
        result = envelope * inverse
        return np.where(
            distance <= self.epsilon,
            1.0,
            np.where(distance < 1.0, result, 0.0),
        )


@dataclass(frozen=True)
class GaussianWeighting(WeightingFunction):
    """Truncated Gaussian weight on a unit-radius support."""

    sharpness: float = 4.0

    def __call__(self, normalized_distance):
        distance = np.asarray(normalized_distance, dtype=float)
        value = np.exp(-float(self.sharpness) * distance**2)
        return np.where(distance < 1.0, value, 0.0)


@dataclass(frozen=True)
class LinearWeighting(WeightingFunction):
    """Linear decay on a unit-radius support."""

    def __call__(self, normalized_distance):
        return np.clip(1.0 - np.asarray(normalized_distance, dtype=float), 0.0, 1.0)


__all__ = [
    "GaussianWeighting",
    "InverseDistanceWeighting",
    "LinearWeighting",
    "WeightingFunction",
]
