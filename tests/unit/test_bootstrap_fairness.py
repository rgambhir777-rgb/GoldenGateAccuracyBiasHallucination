import pytest
from helpers import make_result

from goldengate.fairness.slices import counterfactual_groups, fairness_report, two_proportion_p_value
from goldengate.metrics.bootstrap import bootstrap_statistic, paired_ratio_delta_ci, ratio_ci

# ----------------------------------------------------------------- bootstrap


def test_ratio_ci_brackets_point_estimate_and_is_deterministic():
    nums, dens = [1, 0, 1, 1, 0, 1, 1, 1, 0, 1], [1] * 10
    value, low, high = ratio_ci(nums, dens, samples=500, seed=3)
    assert value == 0.7 and low <= 0.7 <= high and 0.3 <= low < high <= 1.0
    assert ratio_ci(nums, dens, samples=500, seed=3) == (value, low, high)


def test_ratio_ci_edge_cases():
    assert ratio_ci([], []) == (None, None, None)
    assert ratio_ci([0, 0], [0, 0]) == (None, None, None)
    assert ratio_ci([2], [4]) == (0.5, 0.5, 0.5)
    assert ratio_ci([1.0, 1.0, 1.0], [1, 1, 1])[0] == 1.0


def test_ci_narrows_with_more_data():
    small = ratio_ci([1, 0] * 10, [1] * 20, samples=500)
    large = ratio_ci([1, 0] * 200, [1] * 400, samples=500)
    assert (large[2] - large[1]) < (small[2] - small[1])


def test_paired_delta_ci():
    delta, low, high = paired_ratio_delta_ci([1] * 50, [1] * 50, [1] * 40 + [0] * 10, [1] * 50, samples=500)
    assert delta == pytest.approx(-0.2)
    assert high < 0  # significant regression
    same = paired_ratio_delta_ci([1, 0, 1], [1, 1, 1], [1, 0, 1], [1, 1, 1])
    assert same == (0.0, 0.0, 0.0)
    assert paired_ratio_delta_ci([], [], [], []) == (None, None, None)


def test_bootstrap_statistic_stratified():
    low, high = bootstrap_statistic([[1, 1, 1, 1], [0, 0, 0, 0]], lambda a: a[0].mean() - a[1].mean(), samples=200)
    assert low == high == 1.0


# ----------------------------------------------------------------- significance


def test_two_proportion_test_known_values():
    # 8/8 vs 2/8: strongly different
    assert two_proportion_p_value(8, 8, 2, 8) < 0.01
    # identical proportions -> p = 1
    assert two_proportion_p_value(4, 8, 4, 8) == pytest.approx(1.0)
    assert two_proportion_p_value(0, 8, 0, 8) == 1.0
    assert two_proportion_p_value(1, 0, 1, 5) == 1.0
    # textbook example: 45/100 vs 30/100 -> z = 2.19, p ~= 0.0285
    assert two_proportion_p_value(45, 100, 30, 100) == pytest.approx(0.0285, abs=0.001)


# ----------------------------------------------------------------- slices and gaps


def _language_results(non_native_correct: int, n: int = 10):
    out = []
    for i in range(n):
        out.append(make_result(f"n{i}", True, {"language": "native"}, f"g{i}-language"))
        bad = i >= non_native_correct
        out.append(make_result(f"x{i}", not bad, {"language": "non_native"}, f"g{i}-language", refused=bad,
                               present=not bad))
    return out


def test_gap_is_flagged_when_large_and_significant():
    report = fairness_report(_language_results(non_native_correct=3), min_slice_size=8, gap_threshold=0.05,
                             samples=300)
    acc = next(g for g in report.gaps if g.dimension == "language" and g.metric == "accuracy")
    assert acc.best_value == "native" and acc.worst_value == "non_native"
    assert acc.gap == pytest.approx(0.7)
    assert acc.significant and acc.flagged
    assert report.max_accuracy_gap == pytest.approx(0.7) and report.max_accuracy_gap_dimension == "language"
    assert report.max_refusal_gap == pytest.approx(0.7)
    assert any("language" in f for f in report.flagged)


def test_small_gap_is_not_flagged():
    report = fairness_report(_language_results(non_native_correct=9), min_slice_size=8, samples=300)
    acc = next(g for g in report.gaps if g.metric == "accuracy")
    assert acc.gap == pytest.approx(0.1)
    assert not acc.significant and not acc.flagged


def test_min_slice_size_excludes_small_slices():
    report = fairness_report(_language_results(non_native_correct=0, n=5), min_slice_size=8, samples=200)
    assert all(s.below_min_size for s in report.slices)
    assert report.gaps == [] and report.max_accuracy_gap is None


def test_counterfactual_consistency():
    results = [
        make_result("a1", True, {"age_group": "student"}, "g1-age", decision="eligible"),
        make_result("a2", True, {"age_group": "retiree"}, "g1-age", decision="eligible"),
        make_result("b1", True, {"age_group": "student"}, "g2-age", decision="eligible"),
        make_result("b2", False, {"age_group": "retiree"}, "g2-age", refused=True, present=False),
    ]
    groups = counterfactual_groups(results)
    assert [g.consistent for g in groups] == [True, False]
    assert "some variants refused or abstained" in groups[1].differences
    assert any(d.startswith("different decisions") for d in groups[1].differences)
    report = fairness_report(results, min_slice_size=2, samples=200)
    assert report.counterfactual_consistency == 0.5
    assert report.pair_consistency == 0.5


def test_non_counterfactual_items_are_ignored():
    report = fairness_report([make_result("f1", False, {"language": "native"})], samples=100)
    assert report.slices == [] and report.counterfactual_consistency is None
