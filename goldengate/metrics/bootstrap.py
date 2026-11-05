"""Percentile bootstrap confidence intervals for ratio-of-sums metrics."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def ratio_ci(numerators: Sequence[float], denominators: Sequence[float], samples: int = 1000,
             seed: int = 7, alpha: float = 0.05) -> tuple[float | None, float | None, float | None]:
    """Point estimate and (1 - alpha) CI for ``sum(num) / sum(den)`` resampling items.

    Items are resampled with replacement, which treats the item (not the claim
    or citation) as the unit of analysis. Returns ``(value, low, high)``; all
    ``None`` when the denominator is zero.
    """
    num = np.asarray(numerators, dtype=float)
    den = np.asarray(denominators, dtype=float)
    if len(num) == 0 or den.sum() == 0:
        return None, None, None
    value = float(num.sum() / den.sum())
    if len(num) == 1:
        return value, value, value
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(num), size=(samples, len(num)))
    nums, dens = num[idx].sum(axis=1), den[idx].sum(axis=1)
    valid = dens > 0
    ratios = nums[valid] / dens[valid]
    low, high = np.quantile(ratios, [alpha / 2, 1 - alpha / 2])
    return value, float(low), float(high)


def paired_ratio_delta_ci(base_num: Sequence[float], base_den: Sequence[float], cur_num: Sequence[float],
                          cur_den: Sequence[float], samples: int = 1000, seed: int = 7,
                          alpha: float = 0.05) -> tuple[float | None, float | None, float | None]:
    """CI for ratio(current) - ratio(baseline) resampling the *same* items in both runs."""
    arrays = [np.asarray(x, dtype=float) for x in (base_num, base_den, cur_num, cur_den)]
    n = len(arrays[0])
    if n == 0 or arrays[1].sum() == 0 or arrays[3].sum() == 0:
        return None, None, None
    delta = float(arrays[2].sum() / arrays[3].sum() - arrays[0].sum() / arrays[1].sum())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(samples, n))
    bn, bd, cn, cd = (a[idx].sum(axis=1) for a in arrays)
    valid = (bd > 0) & (cd > 0)
    diffs = cn[valid] / cd[valid] - bn[valid] / bd[valid]
    low, high = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return delta, float(low), float(high)


def bootstrap_statistic(groups: Sequence[Sequence[float]], statistic, samples: int = 1000, seed: int = 7,
                        alpha: float = 0.05) -> tuple[float, float]:
    """CI for an arbitrary statistic of several independent groups (stratified bootstrap).

    ``statistic`` receives a list of numpy arrays, one per group, resampled
    within each group, and must return a float.
    """
    rng = np.random.default_rng(seed)
    arrays = [np.asarray(g, dtype=float) for g in groups]
    draws = []
    for _ in range(samples):
        draws.append(statistic([a[rng.integers(0, len(a), len(a))] if len(a) else a for a in arrays]))
    low, high = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    return float(low), float(high)
