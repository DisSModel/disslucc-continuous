"""
LUCC Strategy Picker — Streamlit
=================================
Proof of concept for: pick a Potential strategy, its parameters appear,
run the model — the same shape as dissmodel-sysdyn/dissmodel-ca's
`display_inputs` examples, but resolved *before* a model instance
exists, and aware that Potential parameters are one-entry-per-land-use,
not flat scalars.

Uses synthetic data generated in-script so this runs standalone, with
no example dataset dependency. Swap `_synthetic_gdf()` for a real
GeoDataFrame to use with an actual Lab.

Usage
-----
    streamlit run examples/streamlit/lucc_strategy_picker.py
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import streamlit as st
from shapely.geometry import Point

from dissmodel.core import Environment
from disslucc_continuous import DemandPreComputedValues
from disslucc_continuous.components.registry import (
    resolve_potential,
    resolve_allocation,
    get_potential_param_schema,
    POTENTIAL_STRATEGIES,
    ALLOCATION_STRATEGIES,
)

LU_TYPES = ["f", "d", "outros"]


def _synthetic_gdf(n: int = 40, seed: int = 0) -> gpd.GeoDataFrame:
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


def _render_form_for_schema(schema_model: type, key_prefix: str, container) -> dict:
    """
    Render one Streamlit widget per Pydantic field, generically, based on
    the field's Python type and default — the same idea as
    dissmodel.visualization.display_inputs, but working from a schema
    class instead of an already-built instance's __annotations__.
    """
    values: dict = {}
    for name, field in schema_model.model_fields.items():
        key = f"{key_prefix}_{name}"
        default = field.default if field.default is not None else 0.0
        help_ = field.description
        if field.annotation is bool:
            values[name] = container.checkbox(name, value=bool(default), help=help_, key=key)
        elif field.annotation is int:
            values[name] = container.slider(name, -1, 1000, int(default), help=help_, key=key)
        elif field.annotation is float:
            lo = getattr(field, "metadata", None) and next(
                (c.ge for c in field.metadata if hasattr(c, "ge")), 0.0
            ) or 0.0
            values[name] = container.slider(
                name, float(lo), max(1.0, float(default) + 1.0), float(default),
                step=0.01, help=help_, key=key,
            )
        elif name == "betas":
            values[name] = {}  # driver coefficients edited separately, not via a generic widget
        else:
            values[name] = container.text_input(name, str(default) if default else "", help=help_, key=key)
    return values


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="LUCC Strategy Picker", layout="centered")
st.title("disslucc-continuous — strategy picker")

st.sidebar.title("Strategy")
potential_strategy_name = st.sidebar.selectbox(
    "Potential strategy", sorted(POTENTIAL_STRATEGIES), index=0,
)
allocation_strategy_name = st.sidebar.selectbox(
    "Allocation strategy", sorted(ALLOCATION_STRATEGIES), index=0,
)

# ---------------------------------------------------------------------------
# Parameters — appear based on the strategy picked above
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown(f"**{potential_strategy_name} parameters**")

pot_schema = get_potential_param_schema(potential_strategy_name)
per_lu_values: dict[str, dict] = {}
for lu in LU_TYPES:
    st.sidebar.markdown(f"*{lu}*")
    per_lu_values[lu] = _render_form_for_schema(pot_schema["per_lu"], f"pot_{lu}", st.sidebar)

global_values = _render_form_for_schema(pot_schema["global"], "pot_global", st.sidebar)

n_steps = st.sidebar.slider("Simulation steps", min_value=1, max_value=30, value=5)
run = st.button("Run Simulation")

# ---------------------------------------------------------------------------
# Assemble spec dict the way each strategy's from_spec expects, then build
# ---------------------------------------------------------------------------
if run:
    gdf = _synthetic_gdf()

    if potential_strategy_name == "linear_regression":
        spec = {
            "potential": [{"lu": lu, **per_lu_values[lu]} for lu in LU_TYPES],
            "land_use_no_data": global_values["land_use_no_data"],
        }
    else:  # precomputed
        spec = {
            "potential_columns": {lu: f"suit_{lu}" for lu in LU_TYPES},
            "potential_bias_step": global_values["bias_step"],
        }

    spec["static"]          = {"f": -1, "d": -1, "outros": 0}
    spec["complementar_lu"] = "outros"
    spec["cell_area"]       = 25.0

    env = Environment(end_time=n_steps - 1)

    demand = DemandPreComputedValues(
        annual_demand  = [[70 - i, 20 + i, 10] for i in range(n_steps)],
        land_use_types = LU_TYPES,
    )

    PotentialCls  = resolve_potential(potential_strategy_name, "vector")
    AllocationCls = resolve_allocation(allocation_strategy_name, "vector")

    potential = PotentialCls.from_spec(spec, demand=demand, land_use_types=LU_TYPES, gdf=gdf)
    AllocationCls.from_spec(spec, demand=demand, potential=potential, land_use_types=LU_TYPES, gdf=gdf)
    env.run()

    st.success(f"Ran {n_steps} steps with potential={potential_strategy_name}, allocation={allocation_strategy_name}")
    st.dataframe(gdf[LU_TYPES].describe())
