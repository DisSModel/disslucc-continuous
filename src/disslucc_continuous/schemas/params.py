"""
disslucc_continuous.schemas.params
------------
Pydantic parameter schemas for UI/form generation.

`dissmodel.visualization.display_inputs(instance, st)` (used in the
dissmodel-sysdyn / dissmodel-ca Streamlit examples) reads
`instance.__annotations__` on an already-built Model to render sidebar
widgets. That works for flat scalar attributes on a single fixed model,
but breaks down here for two reasons:

1. A UI needs to know what to ask *before* the object exists — the
   whole point of the strategy registry is to pick the class first,
   then collect its parameters, then call `from_spec(...)`.
2. Potential/Allocation parameters aren't flat: most of them are one
   entry per land use type (e.g. a regression const+betas per `lu`, or
   a suitability column per `lu`), which `display_inputs` has no
   concept of.

These classes describe the *shape of the model spec* consumed by each
strategy's `from_spec` — not the runtime object — so a single pair of
classes covers both the vector and raster implementation of a given
strategy (only the data source passed to `from_spec` differs: `gdf` vs
`backend`, never what the user is asked to fill in).

Each strategy exposes two schemas via the registry:
  - `per_lu`  : one instance of these fields per land use type
  - `global_` : fields that apply once, independent of land use type

A UI walks `land_use_types`, renders `per_lu.model_fields` for each,
renders `global_.model_fields` once, then assembles the result back
into a spec dict shaped the way `from_spec` expects (see
`examples/streamlit/lucc_strategy_picker.py` for a full example) and
calls `StrategyCls.from_spec(spec, ...)`.

`BaseModel.model_json_schema()` on any of these gives a framework-agnostic
JSON Schema (types, defaults, bounds, descriptions) so this is not
tied to Streamlit — the same schema drives a Jupyter widget form, a
future dissmodel-platform React form, or a FastAPI request model.
"""
from __future__ import annotations
from pydantic import BaseModel, Field


# ── potential: linear_regression ─────────────────────────────────────────────

class PotentialLinearRegressionLUParams(BaseModel):
    """One instance per entry in spec['potential'] (i.e. per land use type)."""
    const:  float            = Field(0.0, description="Regression constant (intercept)")
    betas:  dict[str, float] = Field(
        default_factory=dict,
        description="Coefficient per driver column, e.g. {'dist_road': -0.3}",
    )
    is_log: bool = Field(False, description="Apply a log10 transform to the potential surface")


class PotentialLinearRegressionGlobalParams(BaseModel):
    """Fields that apply once, independent of land use type."""
    land_use_no_data: str = Field(
        "outros",
        description="Land use type excluded from Allocation's 'biggest LU' tie-break",
    )


# ── potential: precomputed ───────────────────────────────────────────────────

class PotentialPrecomputedLUParams(BaseModel):
    """One instance per entry in spec['potential_columns'] (i.e. per land use type)."""
    suitability_column: str = Field(
        ...,
        description="Column/band holding this land use's precomputed suitability, in [0, 1]",
    )


class PotentialPrecomputedGlobalParams(BaseModel):
    bias_step: float = Field(
        0.1, ge=0.0,
        description="Additive bias step applied to a land use's potential each time "
                    "Allocation's elasticity saturates",
    )


# ── allocation: clue_like ────────────────────────────────────────────────────

class AllocationClueLikeLUParams(BaseModel):
    """One instance per land use type (spec['allocation'] entry + spec['static'][lu])."""
    static:     int   = Field(-1, ge=-1, le=1, description="-1 = follow demand, 0 = free, 1 = fixed")
    min_value:  float = Field(0.0, ge=0.0, le=1.0)
    max_value:  float = Field(1.0, ge=0.0, le=1.0)
    min_change: float = Field(0.0, ge=0.0, le=1.0)
    max_change: float = Field(1.0, ge=0.0, le=1.0)


class AllocationClueLikeGlobalParams(BaseModel):
    complementar_lu: str = Field(
        ..., description="Land use type that absorbs the residual so all fractions sum to 1"
    )
    cell_area: float = Field(
        25.0, gt=0.0, description="Area represented by one cell/feature, in the model's spatial units"
    )


# ── demand ────────────────────────────────────────────────────────────────────
#
# Demand has no per-land-use fields — the whole [step][lu] matrix is one
# global field, sourced differently per strategy (external CSV vs.
# embedded in the spec). DemandNoLUParams is a shared empty placeholder
# so get_demand_param_schema keeps the same {"per_lu", "global"} shape
# the other two registries use, letting a UI walk all three the same way.

class DemandNoLUParams(BaseModel):
    """Placeholder: demand strategies have no per-land-use parameters."""
    pass


class DemandCsvGlobalParams(BaseModel):
    demand_csv: str = Field(
        ..., description="Path or URI to a CSV with one column per land use type, one row per step"
    )


class DemandInlineGlobalParams(BaseModel):
    values: list[list[float]] = Field(
        ...,
        description="Demand matrix: one row per step, one column per land use type, "
                    "in land_use_types order",
    )
