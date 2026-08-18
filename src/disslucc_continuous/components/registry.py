"""
disslucc_continuous.components.registry
----------------------------------
Strategy registries for Potential and Allocation, keyed by name and
substrate ("vector" | "raster").

This is the data-driven equivalent of what a LuccME modeler used to do
by hand in a .lua script — write `P1 = PotentialCLinearRegression{...}`
instead of `P1 = PotentialCSampleBased{...}` and pass the finished
object to `LuccMEModel{ potential = P1, ... }`. LuccMEModel itself never
imports or knows about any concrete Potential/Allocation class; it only
calls `demand:run()`, `potential:run()`, `allocation:run()` on whatever
was handed to it.

Here the choice is a string in the model spec (TOML) instead of a line
of Lua, so LUCCVectorExecutor / LUCCRasterExecutor can resolve it
without importing any concrete strategy class themselves:

    [model]
    potential_strategy  = "precomputed"   # default: "linear_regression"
    allocation_strategy = "clue_like"     # default: "clue_like"

Every registered class must implement:
  - PotentialProtocol / DemandProtocol-consuming constructor as usual;
  - a `from_spec(cls, spec, *, land_use_types, gdf=None, backend=None,
    demand=None, potential=None, **_ignored)` classmethod that builds an
    instance purely from a resolved model spec dict. `**_ignored` lets
    every strategy accept the same call signature even when it doesn't
    use every kwarg (e.g. PotentialPrecomputed ignores `demand`).

To add a new strategy from outside this package, import this module and
call register_potential_strategy / register_allocation_strategy — no
change to the executors is needed.
"""
from __future__ import annotations

from disslucc_continuous.components.potential.vector import (
    PotentialLinearRegression as _PotVectorLinear,
    PotentialPrecomputed      as _PotVectorPrecomputed,
)
from disslucc_continuous.components.potential.raster import (
    PotentialLinearRegression as _PotRasterLinear,
    PotentialPrecomputed      as _PotRasterPrecomputed,
)
from disslucc_continuous.components.allocation.vector import (
    AllocationClueLike as _AllocVectorClue,
)
from disslucc_continuous.components.allocation.raster import (
    AllocationClueLike as _AllocRasterClue,
)
from disslucc_continuous.components.demand import (
    DemandPreComputedValues as _DemandCsv,
    DemandInline            as _DemandInline,
)
from disslucc_continuous.schemas.params import (
    PotentialLinearRegressionLUParams,
    PotentialLinearRegressionGlobalParams,
    PotentialPrecomputedLUParams,
    PotentialPrecomputedGlobalParams,
    AllocationClueLikeLUParams,
    AllocationClueLikeGlobalParams,
    DemandNoLUParams,
    DemandCsvGlobalParams,
    DemandInlineGlobalParams,
)

POTENTIAL_STRATEGIES: dict[str, dict[str, type]] = {
    "linear_regression": {"vector": _PotVectorLinear,      "raster": _PotRasterLinear},
    "precomputed":       {"vector": _PotVectorPrecomputed, "raster": _PotRasterPrecomputed},
}

ALLOCATION_STRATEGIES: dict[str, dict[str, type]] = {
    "clue_like": {"vector": _AllocVectorClue, "raster": _AllocRasterClue},
}

# Demand is substrate-neutral (no gdf/backend dependency) — both entries
# point at the same classes, kept as a dict for interface symmetry with
# the other two registries.
DEMAND_STRATEGIES: dict[str, dict[str, type]] = {
    "csv":    {"vector": _DemandCsv,    "raster": _DemandCsv},
    "inline": {"vector": _DemandInline, "raster": _DemandInline},
}

DEFAULT_POTENTIAL_STRATEGY  = "linear_regression"
DEFAULT_ALLOCATION_STRATEGY = "clue_like"
DEFAULT_DEMAND_STRATEGY     = "csv"


# ── parameter schemas: what a UI should ask for each strategy ──────────────
#
# Keyed the same way as *_STRATEGIES, but substrate-independent — a UI
# collecting parameters doesn't care whether the run will be vector or
# raster, only what fields to render. "per_lu" fields repeat once per
# land use type; "global" fields apply once to the whole model.

POTENTIAL_PARAM_SCHEMAS: dict[str, dict[str, type]] = {
    "linear_regression": {
        "per_lu": PotentialLinearRegressionLUParams,
        "global": PotentialLinearRegressionGlobalParams,
    },
    "precomputed": {
        "per_lu": PotentialPrecomputedLUParams,
        "global": PotentialPrecomputedGlobalParams,
    },
}

ALLOCATION_PARAM_SCHEMAS: dict[str, dict[str, type]] = {
    "clue_like": {
        "per_lu": AllocationClueLikeLUParams,
        "global": AllocationClueLikeGlobalParams,
    },
}

# Demand has no per-land-use fields (the whole [step][lu] matrix is a
# single global field) — DemandNoLUParams is a shared empty placeholder
# so get_demand_param_schema keeps the same {"per_lu", "global"} shape
# as the other two registries.
DEMAND_PARAM_SCHEMAS: dict[str, dict[str, type]] = {
    "csv":    {"per_lu": DemandNoLUParams, "global": DemandCsvGlobalParams},
    "inline": {"per_lu": DemandNoLUParams, "global": DemandInlineGlobalParams},
}


def register_potential_param_schema(name: str, *, per_lu: type, global_: type) -> None:
    """Attach a parameter schema to a (possibly externally registered) potential strategy."""
    POTENTIAL_PARAM_SCHEMAS[name] = {"per_lu": per_lu, "global": global_}


def register_allocation_param_schema(name: str, *, per_lu: type, global_: type) -> None:
    """Attach a parameter schema to a (possibly externally registered) allocation strategy."""
    ALLOCATION_PARAM_SCHEMAS[name] = {"per_lu": per_lu, "global": global_}


def register_demand_param_schema(name: str, *, global_: type, per_lu: type | None = None) -> None:
    """Attach a parameter schema to a (possibly externally registered) demand strategy."""
    DEMAND_PARAM_SCHEMAS[name] = {"per_lu": per_lu or DemandNoLUParams, "global": global_}


def get_potential_param_schema(name: str) -> dict[str, type]:
    try:
        return POTENTIAL_PARAM_SCHEMAS[name]
    except KeyError as exc:
        raise ValueError(
            f"No parameter schema registered for potential strategy {name!r}. "
            f"Registered: {sorted(POTENTIAL_PARAM_SCHEMAS)}"
        ) from exc


def get_allocation_param_schema(name: str) -> dict[str, type]:
    try:
        return ALLOCATION_PARAM_SCHEMAS[name]
    except KeyError as exc:
        raise ValueError(
            f"No parameter schema registered for allocation strategy {name!r}. "
            f"Registered: {sorted(ALLOCATION_PARAM_SCHEMAS)}"
        ) from exc


def get_demand_param_schema(name: str) -> dict[str, type]:
    try:
        return DEMAND_PARAM_SCHEMAS[name]
    except KeyError as exc:
        raise ValueError(
            f"No parameter schema registered for demand strategy {name!r}. "
            f"Registered: {sorted(DEMAND_PARAM_SCHEMAS)}"
        ) from exc


def register_potential_strategy(
    name: str, *, vector: type | None = None, raster: type | None = None
) -> None:
    """Register (or extend) a potential strategy under `name`."""
    entry = POTENTIAL_STRATEGIES.setdefault(name, {})
    if vector is not None:
        entry["vector"] = vector
    if raster is not None:
        entry["raster"] = raster


def register_allocation_strategy(
    name: str, *, vector: type | None = None, raster: type | None = None
) -> None:
    """Register (or extend) an allocation strategy under `name`."""
    entry = ALLOCATION_STRATEGIES.setdefault(name, {})
    if vector is not None:
        entry["vector"] = vector
    if raster is not None:
        entry["raster"] = raster


def register_demand_strategy(
    name: str, *, vector: type | None = None, raster: type | None = None
) -> None:
    """Register (or extend) a demand strategy under `name`."""
    entry = DEMAND_STRATEGIES.setdefault(name, {})
    if vector is not None:
        entry["vector"] = vector
    if raster is not None:
        entry["raster"] = raster


def resolve_potential(name: str, substrate: str) -> type:
    try:
        return POTENTIAL_STRATEGIES[name][substrate]
    except KeyError as exc:
        available = {k: sorted(v) for k, v in POTENTIAL_STRATEGIES.items()}
        raise ValueError(
            f"Unknown potential_strategy {name!r} for substrate {substrate!r}. "
            f"Registered strategies: {available}"
        ) from exc


def resolve_allocation(name: str, substrate: str) -> type:
    try:
        return ALLOCATION_STRATEGIES[name][substrate]
    except KeyError as exc:
        available = {k: sorted(v) for k, v in ALLOCATION_STRATEGIES.items()}
        raise ValueError(
            f"Unknown allocation_strategy {name!r} for substrate {substrate!r}. "
            f"Registered strategies: {available}"
        ) from exc


def resolve_demand(name: str, substrate: str) -> type:
    try:
        return DEMAND_STRATEGIES[name][substrate]
    except KeyError as exc:
        available = {k: sorted(v) for k, v in DEMAND_STRATEGIES.items()}
        raise ValueError(
            f"Unknown demand_strategy {name!r} for substrate {substrate!r}. "
            f"Registered strategies: {available}"
        ) from exc
