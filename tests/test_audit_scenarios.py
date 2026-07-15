import pytest

from audit.scenarios import SCENARIOS, evaluate
from carrot import sandbox


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_scenario_matches_expected(scenario):
    if scenario.requires_bwrap and not sandbox.bubblewrap_available():
        pytest.skip("bubblewrap (bwrap) is not installed")

    finding = evaluate(scenario)

    assert finding.ok, (
        f"{scenario.id}: expected={scenario.expected!r} outcome={finding.outcome!r} "
        f"— {finding.detail}"
    )
