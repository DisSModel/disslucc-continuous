"""
tests/test_toml_parameters_reach_spec.py
=====================================
Regression test for a real bug found while building a TOML config
generator: dissmodel's CLI TOML loader (`_build_record`) puts
[model.parameters] into `record.parameters`, but does NOT promote it
into `record.resolved_spec["model"]`. Every previous test in this
suite built `resolved_spec` by hand as a flat dict (land_use_types,
complementar_lu, etc. all at the top level) — which sidestepped this
bug entirely, since that's not the shape the real CLI produces.

This test goes through dissmodel.executor.cli._build_record for real,
from an actual TOML file, exactly like `python exec.py run --toml ...`
does — so if the executor ever stops merging `record.parameters` into
`spec` before reading potential_strategy/land_use_types/complementar_lu/
etc., this test fails with a clear signal instead of the silent
"quietly falls back to the code default" failure mode the bug had.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from dissmodel.executor.cli import _build_record
from disslucc_continuous.executors.clue_like_vector_executor import LUCCVectorExecutor

LU_TYPES = ["ferrovia", "pastagem", "resto"]  # deliberately NOT the code's ["f","d","outros"] default


def _write_toml(tmp_path: Path) -> Path:
    toml_path = tmp_path / "model.toml"
    toml_path.write_text(
        f"""
[model.parameters]
n_steps             = 3
land_use_types      = {LU_TYPES!r}
complementar_lu     = "resto"
land_use_no_data    = "resto"
demand_strategy     = "inline"
potential_strategy  = "linear_regression"
allocation_strategy = "clue_like"

[model.demand]
values = [[70.0, 20.0, 10.0], [65.0, 25.0, 10.0], [60.0, 30.0, 10.0]]

[model.static]
ferrovia = -1
pastagem = -1
resto    = 0

[[model.potential]]
lu    = "ferrovia"
const = 0.1

[[model.potential]]
lu    = "pastagem"
const = -0.1

[[model.potential]]
lu    = "resto"
const = 0.0

[[model.allocation]]
lu = "ferrovia"

[[model.allocation]]
lu = "pastagem"

[[model.allocation]]
lu = "resto"
""".replace("['ferrovia', 'pastagem', 'resto']", '["ferrovia", "pastagem", "resto"]')
    )
    return toml_path


def _synthetic_gdf(n: int = 15, seed: int = 0) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(seed)
    return gpd.GeoDataFrame(
        {
            "ferrovia": [0.7] * n,
            "pastagem": [0.2] * n,
            "resto":    [0.1] * n,
            "geometry": [Point(i, 0) for i in range(n)],
        },
        crs="EPSG:4326",
    )


def test_model_parameters_table_reaches_run_via_real_cli_loader(tmp_path):
    """
    land_use_types/complementar_lu/potential_strategy declared inside
    [model.parameters] — deliberately using non-default land use names —
    must actually be honored by the executor when loaded through the
    real CLI path, not silently replaced by the code's ["f","d","outros"]
    / "linear_regression" defaults.
    """
    toml_path = _write_toml(tmp_path)
    args = argparse.Namespace(
        toml=str(toml_path), input="unused", param=None,
        format="auto", column_map=None, band_map=None, output=None,
    )
    record = _build_record(args)

    # Confirms the shape dissmodel's CLI actually produces (this is the
    # documentation of the bug, kept as a guard so a future dissmodel
    # upgrade that changes this shape doesn't silently break the merge
    # this test protects).
    assert "land_use_types" not in record.resolved_spec.get("model", {}), (
        "dissmodel's CLI now promotes [model.parameters] into resolved_spec "
        "directly — the merge workaround in the executors may be redundant; "
        "revisit clue_like_vector_executor.py / clue_like_raster_executor.py."
    )
    assert record.parameters.get("land_use_types") == LU_TYPES

    gdf = _synthetic_gdf()
    executor = LUCCVectorExecutor()
    result = executor.run(gdf, record)

    assert set(result.columns) & set(LU_TYPES) == set(LU_TYPES)
    totals = result[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


def test_wrong_land_use_types_would_have_raised_before_the_fix():
    """
    Sanity check on the bug itself: if the merge is removed, land_use_types
    silently falls back to ["f","d","outros"], which aren't columns in this
    gdf — so the executor would raise a column-missing error instead of
    running. This documents what the pre-fix failure mode looked like.
    """
    gdf = _synthetic_gdf()
    spec_without_merge = {}  # what resolved_spec["model"] alone gives you
    lu_types_fallback = spec_without_merge.get("land_use_types", ["f", "d", "outros"])
    assert not set(lu_types_fallback) & set(gdf.columns), (
        "if this assertion fails, the fallback default happens to match "
        "this gdf's columns and the bug would have gone undetected here too "
        "— same trap as the earlier manual CLI runs."
    )
