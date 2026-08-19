"""
tests/test_toml_builder.py
=====================================
Tests the pure spec-assembly/TOML-serialization logic behind the
Streamlit config generator, and — critically — closes the loop through
the *real* dissmodel CLI TOML loader (dissmodel.executor.cli._build_record)
and the real executor, not a hand-built resolved_spec. This is the same
lesson learned in test_toml_parameters_reach_spec.py: a spec dict built
by hand can look right and still not be what the real pipeline produces.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import tomllib
from shapely.geometry import Point

from dissmodel.executor.cli import _build_record
from disslucc_continuous.executors.clue_like_vector_executor import LUCCVectorExecutor
from disslucc_continuous.toolkit.toml_builder import assemble_spec, spec_to_toml_string

LU_TYPES = ["f", "d", "outros"]


def _synthetic_gdf(n: int = 15, seed: int = 0, suit: bool = False) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(seed)
    data = {
        "f":      [0.7] * n,
        "d":      [0.2] * n,
        "outros": [0.1] * n,
        "geometry": [Point(i, 0) for i in range(n)],
    }
    if suit:
        data.update({
            "suit_f":      rng.uniform(0.0, 1.0, n),
            "suit_d":      rng.uniform(0.0, 1.0, n),
            "suit_outros": rng.uniform(0.0, 1.0, n),
        })
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


def _run_via_real_cli(tmp_path: Path, toml_text: str, gdf: gpd.GeoDataFrame):
    """Writes toml_text to disk, loads it with the real _build_record (same
    path `python exec.py run --toml ...` takes), then runs the real
    LUCCVectorExecutor.run() against an in-memory gdf."""
    toml_path = tmp_path / "generated_model.toml"
    toml_path.write_text(toml_text)

    args = argparse.Namespace(
        toml=str(toml_path), input="unused", param=None,
        format="auto", column_map=None, band_map=None, output=None,
    )
    record = _build_record(args)
    return LUCCVectorExecutor().run(gdf, record)


# ── pure assembly / serialization ───────────────────────────────────────────────

def test_assemble_spec_linear_regression_shape():
    spec = assemble_spec(
        land_use_types      = LU_TYPES,
        n_steps             = 5,
        potential_strategy  = "linear_regression",
        potential_per_lu    = {
            "f": {"const": 0.5, "betas": {"dist_road": -0.2}},
            "d": {"const": -0.3, "betas": {"dist_road": 0.1}},
        },
        potential_global    = {"land_use_no_data": "outros"},
        allocation_strategy = "clue_like",
        allocation_per_lu   = {lu: {"static": -1, "min_value": 0, "max_value": 1} for lu in LU_TYPES},
        allocation_global   = {"complementar_lu": "outros", "cell_area": 25.0},
        demand_strategy     = "csv",
        demand_global       = {"demand_csv": "data/demand.csv"},
    )
    model = spec["model"]
    assert model["parameters"]["potential_strategy"] == "linear_regression"
    assert model["parameters"]["demand_csv"] == "data/demand.csv"
    assert model["parameters"]["complementar_lu"] == "outros"
    assert [p["lu"] for p in model["potential"]] == LU_TYPES
    assert model["driver_columns"]["cols"] == ["dist_road"]  # auto-derived from betas
    assert model["static"] == {lu: -1 for lu in LU_TYPES}


def test_assemble_spec_precomputed_and_inline_shape():
    spec = assemble_spec(
        land_use_types      = LU_TYPES,
        n_steps             = 3,
        potential_strategy  = "precomputed",
        potential_per_lu    = {lu: {"suitability_column": f"suit_{lu}"} for lu in LU_TYPES},
        potential_global    = {"bias_step": 0.2},
        allocation_strategy = "clue_like",
        allocation_per_lu   = {lu: {"static": -1} for lu in LU_TYPES},
        allocation_global   = {"complementar_lu": "outros"},
        demand_strategy     = "inline",
        demand_global       = {"values": [[70, 20, 10], [65, 25, 10], [60, 30, 10]]},
    )
    model = spec["model"]
    assert model["potential_columns"] == {lu: f"suit_{lu}" for lu in LU_TYPES}
    assert model["parameters"]["potential_bias_step"] == 0.2
    assert model["demand"]["values"] == [[70, 20, 10], [65, 25, 10], [60, 30, 10]]
    assert "driver_columns" not in model  # nothing to derive for this strategy


def test_toml_string_round_trips_through_tomllib():
    spec = assemble_spec(
        land_use_types      = LU_TYPES,
        n_steps             = 3,
        potential_strategy  = "linear_regression",
        potential_per_lu    = {lu: {"const": 0.0, "betas": {}} for lu in LU_TYPES},
        potential_global    = {},
        allocation_strategy = "clue_like",
        allocation_per_lu   = {lu: {"static": -1} for lu in LU_TYPES},
        allocation_global   = {"complementar_lu": "outros"},
        demand_strategy     = "csv",
        demand_global       = {"demand_csv": "x.csv"},
    )
    text = spec_to_toml_string(spec)
    parsed = tomllib.loads(text)
    assert parsed == spec


# ── error cases ──────────────────────────────────────────────────────────────

def test_unknown_potential_strategy_raises():
    with pytest.raises(ValueError, match="Unknown potential_strategy"):
        assemble_spec(
            land_use_types=LU_TYPES, n_steps=1,
            potential_strategy="nope", potential_per_lu={}, potential_global={},
            allocation_strategy="clue_like", allocation_per_lu={lu: {} for lu in LU_TYPES},
            allocation_global={"complementar_lu": "outros"},
            demand_strategy="csv", demand_global={"demand_csv": "x.csv"},
        )


def test_precomputed_missing_suitability_column_raises():
    with pytest.raises(ValueError, match="missing suitability_column"):
        assemble_spec(
            land_use_types=LU_TYPES, n_steps=1,
            potential_strategy="precomputed",
            potential_per_lu={"f": {"suitability_column": "suit_f"}},  # missing d, outros
            potential_global={},
            allocation_strategy="clue_like", allocation_per_lu={lu: {} for lu in LU_TYPES},
            allocation_global={"complementar_lu": "outros"},
            demand_strategy="csv", demand_global={"demand_csv": "x.csv"},
        )


def test_inline_demand_wrong_row_width_raises():
    with pytest.raises(ValueError, match="one per land use type"):
        assemble_spec(
            land_use_types=LU_TYPES, n_steps=1,
            potential_strategy="linear_regression",
            potential_per_lu={lu: {"const": 0.0, "betas": {}} for lu in LU_TYPES},
            potential_global={},
            allocation_strategy="clue_like", allocation_per_lu={lu: {"static": -1} for lu in LU_TYPES},
            allocation_global={"complementar_lu": "outros"},
            demand_strategy="inline", demand_global={"values": [[70, 20]]},  # only 2 cols, need 3
        )


# ── the real loop: generated TOML -> real CLI loader -> real executor ─────────

def test_generated_toml_runs_through_real_cli_linear_regression_csv(tmp_path):
    gdf = _synthetic_gdf()
    (tmp_path / "demand.csv").write_text("f,d,outros\n70,20,10\n65,25,10\n60,30,10\n")

    spec = assemble_spec(
        land_use_types      = LU_TYPES,
        n_steps             = 3,
        potential_strategy  = "linear_regression",
        potential_per_lu    = {
            "f": {"const": 0.1, "betas": {}},
            "d": {"const": -0.1, "betas": {}},
            "outros": {"const": 0.0, "betas": {}},
        },
        potential_global    = {"land_use_no_data": "outros"},
        allocation_strategy = "clue_like",
        allocation_per_lu   = {lu: {"static": -1 if lu != "outros" else 0} for lu in LU_TYPES},
        allocation_global   = {"complementar_lu": "outros"},
        demand_strategy     = "csv",
        demand_global       = {"demand_csv": str(tmp_path / "demand.csv")},
    )
    result = _run_via_real_cli(tmp_path, spec_to_toml_string(spec), gdf)

    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def test_generated_toml_runs_through_real_cli_precomputed_inline(tmp_path):
    gdf = _synthetic_gdf(suit=True)

    spec = assemble_spec(
        land_use_types      = LU_TYPES,
        n_steps             = 3,
        potential_strategy  = "precomputed",
        potential_per_lu    = {lu: {"suitability_column": f"suit_{lu}"} for lu in LU_TYPES},
        potential_global    = {"bias_step": 0.1},
        allocation_strategy = "clue_like",
        allocation_per_lu   = {lu: {"static": -1 if lu != "outros" else 0} for lu in LU_TYPES},
        allocation_global   = {"complementar_lu": "outros"},
        demand_strategy     = "inline",
        demand_global       = {"values": [[70, 20, 10], [65, 25, 10], [60, 30, 10]]},
    )
    result = _run_via_real_cli(tmp_path, spec_to_toml_string(spec), gdf)

    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)
