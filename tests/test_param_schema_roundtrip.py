"""
tests/test_param_schema_roundtrip.py
=====================================
Proves the chain a UI would exercise: pick a strategy -> read its
parameter schema -> collect values (here: schema defaults, standing in
for what a user would type into a form) -> assemble a spec dict ->
StrategyCls.from_spec(spec, ...) -> run.

This is the non-UI half of what examples/streamlit/lucc_strategy_picker.py
does interactively. If a strategy's param schema field names drift from
what from_spec actually reads, this test catches it.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from dissmodel.core import Environment
from disslucc_continuous import DemandPreComputedValues
from disslucc_continuous.components.registry import (
    resolve_potential,
    resolve_allocation,
    get_potential_param_schema,
    get_allocation_param_schema,
    POTENTIAL_STRATEGIES,
    ALLOCATION_STRATEGIES,
)

LU_TYPES = ["f", "d", "outros"]


def _synthetic_gdf(n: int = 15, seed: int = 0) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(seed)
    return gpd.GeoDataFrame(
        {
            "f":           [0.7] * n,
            "d":           [0.2] * n,
            "outros":      [0.1] * n,
            "suit_f":      rng.uniform(0.0, 1.0, n),
            "suit_d":      rng.uniform(0.0, 1.0, n),
            "suit_outros": rng.uniform(0.0, 1.0, n),
            "geometry":    [Point(i, 0) for i in range(n)],
        },
        crs="EPSG:4326",
    )


@pytest.mark.parametrize("potential_strategy_name", sorted(POTENTIAL_STRATEGIES))
def test_schema_defaults_assemble_into_a_runnable_spec(potential_strategy_name):
    """Every registered potential strategy's schema defaults must produce
    a spec that its own from_spec accepts and that actually runs."""
    schema = get_potential_param_schema(potential_strategy_name)
    global_defaults = schema["global"]().model_dump() if _all_optional(schema["global"]) else None

    gdf = _synthetic_gdf()

    if potential_strategy_name == "linear_regression":
        per_lu_defaults = schema["per_lu"]().model_dump()  # all-optional -> safe to default-construct
        spec = {
            "potential": [{"lu": lu, **per_lu_defaults} for lu in LU_TYPES],
            "land_use_no_data": global_defaults["land_use_no_data"],
        }
    elif potential_strategy_name == "precomputed":
        # suitability_column has no sensible default (it must name a real
        # column), so this strategy's per-lu values come from the dataset
        # instead of the schema default.
        spec = {
            "potential_columns": {lu: f"suit_{lu}" for lu in LU_TYPES},
            "potential_bias_step": global_defaults["bias_step"],
        }
    else:
        pytest.skip(f"no spec-assembly rule wired for {potential_strategy_name!r} in this test")

    spec["static"]          = {lu: -1 for lu in LU_TYPES[:-1]} | {LU_TYPES[-1]: 0}
    spec["complementar_lu"] = LU_TYPES[-1]
    spec["cell_area"]       = 25.0

    env = Environment(end_time=2)

    demand = DemandPreComputedValues(
        annual_demand  = [[70, 20, 10], [65, 25, 10], [60, 30, 10]],
        land_use_types = LU_TYPES,
    )

    PotentialCls  = resolve_potential(potential_strategy_name, "vector")
    AllocationCls = resolve_allocation("clue_like", "vector")

    potential = PotentialCls.from_spec(spec, demand=demand, land_use_types=LU_TYPES, gdf=gdf)
    AllocationCls.from_spec(spec, demand=demand, potential=potential, land_use_types=LU_TYPES, gdf=gdf)
    env.run()

    totals = gdf[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def _all_optional(schema_model) -> bool:
    return all(not f.is_required() for f in schema_model.model_fields.values())


def test_every_registered_strategy_exposes_a_json_schema():
    """Any UI framework should be able to introspect every strategy generically."""
    for name in POTENTIAL_STRATEGIES:
        schema = get_potential_param_schema(name)
        assert schema["per_lu"].model_json_schema()["properties"]
        assert schema["global"].model_json_schema() is not None
    for name in ALLOCATION_STRATEGIES:
        schema = get_allocation_param_schema(name)
        assert schema["per_lu"].model_json_schema()["properties"]
        assert schema["global"].model_json_schema() is not None
