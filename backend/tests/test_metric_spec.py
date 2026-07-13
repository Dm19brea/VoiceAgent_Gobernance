"""M4 — MetricSpec skeleton: declarative metric table (design D1, spec R1)."""

import dataclasses

from src.domain.scoring.metric_spec import METRIC_SPECS, MetricSpec, identity, to_percent


def test_metric_spec_is_a_frozen_dataclass_with_expected_fields() -> None:
    fields = {f.name for f in dataclasses.fields(MetricSpec)}

    assert fields == {"code", "dimension", "criterion", "unit", "weight", "transform", "normalize"}
    assert dataclasses.fields(MetricSpec)[0].name == "code"


def test_metric_spec_instances_are_frozen() -> None:
    spec = METRIC_SPECS[0]

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        spec.code = "changed"  # type: ignore[misc]


def test_identity_returns_the_value_unchanged() -> None:
    assert identity(5.0) == 5.0


def test_to_percent_rescales_a_ratio_to_a_percentage() -> None:
    assert to_percent(0.87) == 87.0


def test_metric_specs_table_is_not_empty() -> None:
    assert len(METRIC_SPECS) >= 11


def test_metric_specs_codes_are_unique() -> None:
    codes = [spec.code for spec in METRIC_SPECS]

    assert len(codes) == len(set(codes))
