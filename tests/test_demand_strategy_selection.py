"""
tests/test_demand_strategy_selection.py
=====================================
Same proof as test_executor_strategy_selection.py, but for demand:
LUCCVectorExecutor resolves DemandPreComputedValues vs. DemandInline via
`model.demand_strategy` in the spec, never importing a concrete demand
class itself. "inline" needs no demand_csv at all — the matrix comes
straight from [model.demand].values.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from dissmodel.executor import ExperimentRecord
from disslucc_continuous.executors.clue_like_vector_executor import LUCCVectorExecutor

LU_TYPES = ["f", "d", "outros"]


def _synthetic_gdf(n: int = 15, seed: int = 0) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(seed)
    return gpd.GeoDataFrame(
        {
            "f":      [0.7] * n,
            "d":      [0.2] * n,
            "outros": [0.1] * n,
            "geometry": [Point(i, 0) for i in range(n)],
        },
        crs="EPSG:4326",
    )


def _record(spec_model: dict, parameters: dict | None = None) -> ExperimentRecord:
    return ExperimentRecord(
        model_name    = "lucc_vector",
        source        = {"uri": "unused"},
        parameters    = parameters or {"n_steps": 3},
        resolved_spec = {"model": spec_model},
    )


def test_inline_demand_strategy_needs_no_csv():
    """
    demand_strategy="inline" runs with no demand_csv in parameters at
    all — the matrix comes straight from [model.demand].values in the
    spec. Proves the executor never hardcodes 'read demand_csv'.
    """
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "demand_strategy": "inline",
        "demand": {
            "values": [
                [70.0, 20.0, 10.0],
                [65.0, 25.0, 10.0],
                [60.0, 30.0, 10.0],
            ],
        },
        "potential": [
            {"lu": "f", "const": 0.1, "betas": {}},
            {"lu": "d", "const": -0.1, "betas": {}},
        ],
    }
    executor = LUCCVectorExecutor()
    # no demand_csv key anywhere in parameters
    result = executor.run(gdf, _record(spec, parameters={"n_steps": 3}))

    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def test_default_demand_strategy_still_reads_csv():
    """No demand_strategy key -> default 'csv', same as before this change."""
    import disslucc_continuous.executors.clue_like_vector_executor as mod

    gdf = _synthetic_gdf(seed=2)
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "potential": [
            {"lu": "f", "const": 0.1, "betas": {}},
            {"lu": "d", "const": -0.1, "betas": {}},
        ],
    }
    original_read_text = mod.read_text
    mod.read_text = lambda _uri: "f,d,outros\n70,20,10\n65,25,10\n60,30,10\n"
    try:
        executor = LUCCVectorExecutor()
        result = executor.run(gdf, _record(spec, parameters={"demand_csv": "unused", "n_steps": 3}))
    finally:
        mod.read_text = original_read_text

    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def test_unknown_demand_strategy_raises_clear_error():
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "demand_strategy": "does_not_exist",
        "potential": [{"lu": "f", "const": 0.1}, {"lu": "d", "const": -0.1}],
    }
    executor = LUCCVectorExecutor()
    with pytest.raises(ValueError, match="Unknown demand_strategy"):
        executor.run(gdf, _record(spec, parameters={"n_steps": 3}))


def test_inline_demand_missing_values_raises_clear_error():
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "demand_strategy": "inline",
        # [model.demand].values missing on purpose
        "potential": [{"lu": "f", "const": 0.1}, {"lu": "d", "const": -0.1}],
    }
    executor = LUCCVectorExecutor()
    with pytest.raises(ValueError, match="demand_strategy='inline'"):
        executor.run(gdf, _record(spec, parameters={"n_steps": 3}))


def test_csv_demand_strategy_without_demand_csv_raises_clear_error():
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        # demand_strategy defaults to "csv"
        "potential": [{"lu": "f", "const": 0.1}, {"lu": "d", "const": -0.1}],
    }
    executor = LUCCVectorExecutor()
    with pytest.raises(ValueError, match="demand_strategy='csv'"):
        executor.run(gdf, _record(spec, parameters={"n_steps": 3}))  # no demand_csv key
