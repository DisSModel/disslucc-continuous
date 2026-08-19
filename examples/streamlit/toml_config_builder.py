"""
TOML Config Generator — Streamlit
=================================
Pick potential/allocation/demand strategies, fill in the parameters
that appear for each, get a downloadable model.toml.

Pure logic (spec assembly + TOML serialization) lives in
disslucc_continuous.toolkit.toml_builder and
disslucc_continuous.components.registry — this file is UI only. If a
new strategy is registered in either module, it shows up here
automatically (new selectbox option); nothing in this file needs to
change unless the new strategy's per-lu/global fields need a widget
type this form doesn't already handle (see _render_form_for_schema).

Data-awareness: uploading a dataset at the top turns land use types,
driver columns (betas), and suitability columns from free-text fields
into selects/multiselects sourced from the file's real columns — so a
typo can't silently produce a TOML that references a column that
doesn't exist. Without an upload, every field falls back to free text,
so the generator still works for sketching a TOML before data is in
hand.

Install:
    pip install disslucc-continuous[toolkit]

Run:
    streamlit run examples/streamlit/toml_config_builder.py
"""
from __future__ import annotations

import streamlit as st

from disslucc_continuous.components.registry import (
    POTENTIAL_STRATEGIES,
    ALLOCATION_STRATEGIES,
    DEMAND_STRATEGIES,
    get_potential_param_schema,
    get_allocation_param_schema,
    get_demand_param_schema,
)
from disslucc_continuous.toolkit.toml_builder import assemble_spec, spec_to_toml_string


def _read_columns(uploaded_file) -> list[str] | None:
    """
    Best-effort column list from an uploaded dataset. Returns None
    (falling back to free text everywhere) if nothing was uploaded or
    it couldn't be read — never raises, since this is a convenience
    layer, not a requirement.
    """
    if uploaded_file is None:
        return None
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            import pandas as pd
            return list(pd.read_csv(uploaded_file, nrows=5).columns)
        import geopandas as gpd
        gdf = gpd.read_file(uploaded_file)
        return [c for c in gdf.columns if c != "geometry"]
    except Exception as exc:
        st.error(f"Couldn't read columns from the uploaded file: {exc}")
        return None


def _render_form_for_schema(
    schema_model: type, key_prefix: str, container, available_columns: list[str] | None = None,
) -> dict:
    """
    One widget per Pydantic field, generically, based on the field's
    Python type and default — same approach as
    dissmodel.visualization.display_inputs, applied to a schema class
    instead of an already-built instance.

    Fields that name a dataset column (betas, suitability_column) get a
    select/multiselect sourced from available_columns when a dataset
    was uploaded, instead of a free-text field the user could typo.
    """
    values: dict = {}
    for name, field in schema_model.model_fields.items():
        key = f"{key_prefix}_{name}"
        required = field.is_required()
        default = field.default if not required else None

        if field.annotation is bool:
            values[name] = container.checkbox(name, value=bool(default), help=field.description, key=key)
        elif field.annotation is int:
            values[name] = container.number_input(
                name, value=int(default) if default is not None else 0,
                step=1, help=field.description, key=key,
            )
        elif field.annotation is float:
            values[name] = container.number_input(
                name, value=float(default) if default is not None else 0.0,
                step=0.01, format="%.4f", help=field.description, key=key,
            )
        elif name == "betas":
            if available_columns:
                chosen = container.multiselect(
                    name, options=available_columns,
                    help="driver columns from the uploaded dataset", key=key,
                )
                values[name] = {
                    col: container.number_input(
                        f"  {col} coefficient", value=0.0, step=0.01, format="%.4f", key=f"{key}_{col}",
                    )
                    for col in chosen
                }
            else:
                raw = container.text_input(
                    name, value="", help="comma-separated column=coef pairs, e.g. dist_road=-0.2,uc_us=0.17",
                    key=key,
                )
                pairs = [p.split("=") for p in raw.split(",") if "=" in p]
                values[name] = {k.strip(): float(v) for k, v in pairs}
        elif name == "suitability_column" and available_columns:
            values[name] = container.selectbox(name, options=available_columns, key=key)
        else:
            values[name] = container.text_input(
                name, value=str(default) if default is not None else "",
                help=field.description, key=key,
            )
    return values


st.set_page_config(page_title="disslucc-continuous — TOML config generator", layout="centered")
st.title("model.toml generator")
st.caption("Pick strategies, fill in parameters, download a TOML ready for LUCCVectorExecutor / LUCCRasterExecutor.")

# ---------------------------------------------------------------------------
# Optional dataset upload — makes every column-name field below a
# validated select instead of free text. Skip this and everything still
# works, just without the guard rail.
# ---------------------------------------------------------------------------
st.header("0. Dataset (optional, but recommended)")
uploaded = st.file_uploader(
    "Upload the vector dataset this model will run against (.gpkg, .geojson, .csv, or a zipped shapefile) "
    "to turn column-name fields below into validated selects instead of free text.",
    type=["gpkg", "geojson", "json", "csv", "zip"],
)
available_columns = _read_columns(uploaded)
if available_columns:
    st.success(f"{len(available_columns)} columns found: {', '.join(available_columns)}")

# ---------------------------------------------------------------------------
# Global model settings
# ---------------------------------------------------------------------------
st.header("1. Model")
if available_columns:
    land_use_types = st.multiselect("Land use types (from the uploaded dataset)", options=available_columns)
else:
    land_use_types_raw = st.text_input("Land use types (comma-separated)", value="f, d, outros")
    land_use_types = [lu.strip() for lu in land_use_types_raw.split(",") if lu.strip()]
n_steps = st.number_input("Number of steps", min_value=1, value=7, step=1)

if not land_use_types:
    st.warning("Select or enter at least one land use type to continue.")
    st.stop()

# ---------------------------------------------------------------------------
# Strategy pickers
# ---------------------------------------------------------------------------
st.header("2. Strategies")
col1, col2, col3 = st.columns(3)
potential_strategy  = col1.selectbox("Potential",  sorted(POTENTIAL_STRATEGIES))
allocation_strategy = col2.selectbox("Allocation", sorted(ALLOCATION_STRATEGIES))
demand_strategy     = col3.selectbox("Demand",     sorted(DEMAND_STRATEGIES))

# columns already claimed by land_use_types shouldn't also be offered as
# driver/suitability columns
remaining_columns = (
    [c for c in available_columns if c not in land_use_types] if available_columns else None
)

# ---------------------------------------------------------------------------
# Potential parameters
# ---------------------------------------------------------------------------
st.header("3. Potential parameters")
pot_schema = get_potential_param_schema(potential_strategy)
potential_per_lu: dict[str, dict] = {}
for lu in land_use_types:
    with st.expander(f"potential — {lu}", expanded=False):
        potential_per_lu[lu] = _render_form_for_schema(
            pot_schema["per_lu"], f"pot_{lu}", st, available_columns=remaining_columns,
        )
potential_global = _render_form_for_schema(pot_schema["global"], "pot_global", st)

# ---------------------------------------------------------------------------
# Allocation parameters
# ---------------------------------------------------------------------------
st.header("4. Allocation parameters")
alloc_schema = get_allocation_param_schema(allocation_strategy)
allocation_per_lu: dict[str, dict] = {}
for lu in land_use_types:
    with st.expander(f"allocation — {lu}", expanded=False):
        allocation_per_lu[lu] = _render_form_for_schema(alloc_schema["per_lu"], f"alloc_{lu}", st)
allocation_global = _render_form_for_schema(alloc_schema["global"], "alloc_global", st)
# complementar_lu is better as a selectbox over the actual land use types
# than a free-text field — override the generic text_input rendered above.
allocation_global["complementar_lu"] = st.selectbox(
    "complementar_lu", land_use_types,
    index=land_use_types.index(allocation_global["complementar_lu"])
        if allocation_global.get("complementar_lu") in land_use_types else 0,
)

# ---------------------------------------------------------------------------
# Demand parameters
# ---------------------------------------------------------------------------
st.header("5. Demand parameters")
demand_schema = get_demand_param_schema(demand_strategy)
demand_global = _render_form_for_schema(demand_schema["global"], "demand_global", st)
if demand_strategy == "inline":
    st.caption("One row per step, comma-separated, one line per row — values in "
               f"{land_use_types} order. Needs at least n_steps ({int(n_steps)}) rows.")
    default_row  = ",".join("10" for _ in land_use_types)
    default_rows = "\n".join(default_row for _ in range(int(n_steps)))
    raw_rows = st.text_area("values", value=default_rows, key="demand_inline_rows")
    demand_global["values"] = [
        [float(x) for x in line.split(",")] for line in raw_rows.strip().splitlines() if line.strip()
    ]

# ---------------------------------------------------------------------------
# Assemble + preview + download
# ---------------------------------------------------------------------------
st.header("6. Generated TOML")
try:
    spec = assemble_spec(
        land_use_types      = land_use_types,
        n_steps             = int(n_steps),
        potential_strategy  = potential_strategy,
        potential_per_lu    = potential_per_lu,
        potential_global    = potential_global,
        allocation_strategy = allocation_strategy,
        allocation_per_lu   = allocation_per_lu,
        allocation_global   = allocation_global,
        demand_strategy     = demand_strategy,
        demand_global       = demand_global,
    )
    toml_text = spec_to_toml_string(spec)
    st.code(toml_text, language="toml")
    st.download_button("Download model.toml", data=toml_text, file_name="model.toml", mime="application/toml")
except ValueError as exc:
    st.error(f"Can't generate TOML yet: {exc}")
