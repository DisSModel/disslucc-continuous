"""
tests/test_toml_config_builder_app.py
=====================================
Headless UI test for examples/streamlit/toml_config_builder.py using
Streamlit's AppTest (no browser needed). Exercises the actual app
script, not just the pure toolkit.toml_builder functions it calls —
this is what caught a real bug during development: the default
n_steps=7 didn't match the default 3-row inline demand textarea,
producing a TOML that parsed fine but crashed mid-simulation with
IndexError. That failure mode is now a ValueError raised by
assemble_spec() itself (see test_toml_builder.py) and the app's
default textarea now always has n_steps rows — this test locks both.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point
from streamlit.testing.v1 import AppTest

from dissmodel.executor.cli import _build_record
from disslucc_continuous.executors.clue_like_vector_executor import LUCCVectorExecutor

APP_PATH = str(Path(__file__).resolve().parent.parent / "examples" / "streamlit" / "toml_config_builder.py")


def test_app_loads_with_no_exceptions():
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)
    assert not at.exception


def test_app_default_state_generates_valid_toml():
    """Default widget values (linear_regression / clue_like / csv) must
    produce either a valid TOML preview or a clear st.error — never a
    silent crash — even though demand_csv is empty by default."""
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)
    assert not at.exception
    # demand_csv is empty by default -> assemble_spec raises -> shown as st.error,
    # not a crash.
    assert len(at.error) == 1
    assert "demand_csv" in at.error[0].value


def test_app_switching_strategies_keeps_row_count_in_sync_with_n_steps():
    """
    Regression test for the exact bug found manually: switching to
    demand_strategy='inline' must default the textarea to n_steps rows,
    not a fixed count that silently falls out of sync when n_steps changes.
    """
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)
    at.selectbox[2].select("inline").run(timeout=15)  # demand selectbox

    n_steps = int(at.number_input[0].value)  # first number_input on the page is n_steps
    rows_widget = next(w for w in at.text_area if w.key == "demand_inline_rows")
    n_rows = len([line for line in rows_widget.value.strip().splitlines() if line.strip()])
    assert n_rows >= n_steps


def test_generated_toml_from_real_ui_interaction_runs_through_real_cli(tmp_path: Path):
    """
    Full loop: drive the actual Streamlit widgets (not the pure
    toolkit functions directly) to select potential='precomputed',
    demand='inline', fill in suitability columns, read the TOML the app
    displays, then run that exact text through the real CLI loader and
    the real executor.
    """
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)
    at.selectbox[0].select("precomputed").run(timeout=15)  # potential
    at.selectbox[2].select("inline").run(timeout=15)       # demand

    for ti in at.text_input:
        if ti.key and "suitability_column" in ti.key:
            lu = ti.key.split("_")[1]
            ti.set_value(f"suit_{lu}")
    at.run(timeout=15)

    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(at.code) == 1
    toml_text = at.code[0].value

    toml_path = tmp_path / "model.toml"
    toml_path.write_text(toml_text)
    args = argparse.Namespace(
        toml=str(toml_path), input="unused", param=None,
        format="auto", column_map=None, band_map=None, output=None,
    )
    record = _build_record(args)

    n = 15
    rng = np.random.default_rng(0)
    gdf = gpd.GeoDataFrame(
        {
            "f": [0.7] * n, "d": [0.2] * n, "outros": [0.1] * n,
            "suit_f": rng.uniform(0, 1, n), "suit_d": rng.uniform(0, 1, n),
            "suit_outros": rng.uniform(0, 1, n),
            "geometry": [Point(i, 0) for i in range(n)],
        },
        crs="EPSG:4326",
    )
    result = LUCCVectorExecutor().run(gdf, record)
    totals = result[["f", "d", "outros"]].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)


# ── data-aware mode: real dataset uploaded, columns drive the widgets ──────────

LAB1_ZIP    = Path(__file__).resolve().parent.parent / "examples" / "data" / "input" / "csAC.zip"
LAB1_DEMAND = Path(__file__).resolve().parent.parent / "examples" / "data" / "input" / "examples_demand_lab1.csv"


def test_uploading_a_dataset_populates_land_use_types_from_real_columns():
    """
    Regression test for the gap raised directly: without an upload,
    land_use_types was free text with zero connection to any real
    dataset. Uploading a file must replace that with a multiselect
    sourced from the file's actual columns.
    """
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    data = LAB1_ZIP.read_bytes()
    at.file_uploader[0].set_value(("csAC.zip", data, "application/zip"))
    at.run(timeout=20)

    assert not at.exception
    assert at.success, "expected a st.success message reporting detected columns"
    lu_multiselect = at.multiselect[0]
    assert lu_multiselect.label.startswith("Land use types")
    # real columns from csAC.zip, not a hardcoded default
    assert "f" in lu_multiselect.options
    assert "assentamen" in lu_multiselect.options


def test_full_loop_real_upload_real_column_selection_runs_through_real_cli():
    """
    The strongest version of the loop test: an actual uploaded dataset,
    actual columns picked via multiselect (land use types AND driver
    columns for the regression betas), run through the real CLI loader
    and the real executor against the real Lab1 data — not synthetic.
    """
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=15)

    data = LAB1_ZIP.read_bytes()
    at.file_uploader[0].set_value(("csAC.zip", data, "application/zip"))
    at.run(timeout=20)

    at.multiselect[0].set_value(["f", "d", "outros"]).run(timeout=20)

    betas_widget = next(m for m in at.multiselect if m.key == "pot_f_betas")
    betas_widget.set_value(["assentamen", "uc_us"]).run(timeout=20)

    for ti in at.text_input:
        if ti.key == "demand_global_demand_csv":
            ti.set_value(str(LAB1_DEMAND))
    at.run(timeout=20)

    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(at.code) == 1
    toml_text = at.code[0].value
    assert '"assentamen"' in toml_text  # driver_columns derived from the real selection

    toml_path = tempfile.mkdtemp()
    toml_file = Path(toml_path) / "model.toml"
    toml_file.write_text(toml_text)
    args = argparse.Namespace(
        toml=str(toml_file), input=str(LAB1_ZIP), param=None,
        format="auto", column_map=None, band_map=None, output=None,
    )
    record = _build_record(args)

    from dissmodel.io import load_dataset
    gdf, _ = load_dataset(str(LAB1_ZIP))
    result = LUCCVectorExecutor().run(gdf, record)
    totals = result[["f", "d", "outros"]].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)
