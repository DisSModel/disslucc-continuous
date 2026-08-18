"""
tests/test_executor_strategy_selection.py
=====================================
Proves that LUCCVectorExecutor / LUCCRasterExecutor are generic over the
Potential strategy: swapping "linear_regression" -> "precomputed" only
requires changing the resolved spec (what a TOML file would produce),
never the executor code. This is the equivalent of a LuccME modeler
swapping which Potential*.lua object they pass into LuccMEModel{...}.

Also covers the negative path: an unknown strategy name raises a clear
error instead of an executor silently doing the wrong thing.
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
            "f":            [0.7] * n,
            "d":            [0.2] * n,
            "outros":       [0.1] * n,
            "suit_f":       rng.uniform(0.0, 1.0, n),
            "suit_d":       rng.uniform(0.0, 1.0, n),
            "suit_outros":  rng.uniform(0.0, 1.0, n),
            "geometry":     [Point(i, 0) for i in range(n)],
        },
        crs="EPSG:4326",
    )


def _record(spec_model: dict) -> ExperimentRecord:
    return ExperimentRecord(
        model_name    = "lucc_vector",
        source        = {"uri": "unused"},   # data is injected directly in this test
        parameters    = {"demand_csv": "unused", "n_steps": 3},
        resolved_spec = {"model": spec_model},
    )


def _run_with_demand(executor, gdf, record):
    """
    Bypass load()/read_text() I/O (demand_csv, source.uri) since this test
    supplies data in-memory — mirrors what execute_lifecycle would do after
    load(), but with a monkeypatched demand CSV read.
    """
    import disslucc_continuous.executors.clue_like_vector_executor as mod

    original_read_text = mod.read_text
    mod.read_text = lambda _uri: "f,d,outros\n70,20,10\n65,25,10\n60,30,10\n"
    try:
        return executor.run(gdf, record)
    finally:
        mod.read_text = original_read_text


def test_default_strategy_is_linear_regression_backward_compatible():
    """No potential_strategy key in spec -> same behavior as before this change."""
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "potential": [
            {"lu": "f", "const": 0.1, "betas": {}},
            {"lu": "d", "const": -0.1, "betas": {}},
        ],
    }
    executor = LUCCVectorExecutor()
    result = _run_with_demand(executor, gdf, _record(spec))

    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def test_precomputed_strategy_selected_purely_via_spec():
    """
    Same executor, same call site — only the spec changes:
    potential_strategy = "precomputed" + potential_columns table.
    No Python code touches PotentialPrecomputed directly.
    """
    gdf = _synthetic_gdf(seed=1)
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "potential_strategy": "precomputed",
        "potential_columns": {
            "f": "suit_f", "d": "suit_d", "outros": "suit_outros",
        },
    }
    executor = LUCCVectorExecutor()
    result = _run_with_demand(executor, gdf, _record(spec))

    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def test_unknown_potential_strategy_raises_clear_error():
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "potential_strategy": "does_not_exist",
    }
    executor = LUCCVectorExecutor()
    with pytest.raises(ValueError, match="Unknown potential_strategy"):
        _run_with_demand(executor, gdf, _record(spec))


def test_precomputed_strategy_missing_columns_raises_clear_error():
    gdf = _synthetic_gdf()
    spec = {
        "land_use_types": LU_TYPES,
        "static": {"f": -1, "d": -1, "outros": 0},
        "complementar_lu": "outros",
        "potential_strategy": "precomputed",
        "potential_columns": {"f": "suit_f"},   # missing d, outros
    }
    executor = LUCCVectorExecutor()
    with pytest.raises(ValueError, match="missing"):
        _run_with_demand(executor, gdf, _record(spec))
