"""
disslucc_continuous.components.demand.inline
----------------------------------
Demand strategy whose matrix comes straight from the resolved model
spec instead of a separate CSV file.

Runtime behavior is identical to DemandPreComputedValues — same setup/
execute/DemandProtocol methods — so this simply subclasses it and only
overrides from_spec, where the two strategies actually differ: where
the [step][land_use] matrix comes from, not what is done with it.

Useful for small examples/tests that shouldn't need an extra data
asset, and demonstrates that AllocationClueLike / the executors are as
decoupled from "how demand is sourced" as they already are from "which
potential strategy computed the suitability surface".
"""
from __future__ import annotations

from .precomputed import DemandPreComputedValues


class DemandInline(DemandPreComputedValues):
    """
    Same as DemandPreComputedValues, but reads its demand matrix from
    `spec["demand"]["values"]` instead of an external CSV — no
    demand_csv, no I/O in from_spec:

        [model.parameters]
        demand_strategy = "inline"

        [model.demand]
        # one row per step, one column per land use, in land_use_types order
        values = [
            [137878.17, 19982.63, 6489.20],
            [137622.22, 20238.58, 6489.20],
        ]
    """

    @classmethod
    def from_spec(cls, spec: dict, *, land_use_types: list[str], **_ignored):
        values = spec.get("demand", {}).get("values")
        if not values:
            raise ValueError(
                "demand_strategy='inline' requires [model.demand].values in "
                "the spec — a list of [land_use...] rows, one per step."
            )
        return cls(annual_demand=values, land_use_types=land_use_types)
