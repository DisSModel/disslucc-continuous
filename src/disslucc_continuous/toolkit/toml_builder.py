"""
disslucc_continuous.toolkit.toml_builder
----------------------------------
Pure functions that assemble a resolved model spec (the nested dict a
TOML file parses into) from per-strategy parameter values, and
serialize it to a TOML string.

Deliberately has no UI dependency (no Streamlit import here) so it can
be unit-tested headlessly and reused by any front-end — a Streamlit
form, a CLI wizard, a future dissmodel-platform React form.

One assembler function per registered strategy, keyed the same way as
`disslucc_continuous.components.registry`. Each assembler returns
`(parameters_fragment, model_fragment)`:
  - parameters_fragment merges into [model.parameters] (scalars read via
    `params`/`spec.get(...)` after the executor's params/spec merge —
    see the fix in clue_like_vector_executor.py for why this table
    matters)
  - model_fragment merges into the top-level [model.*] tables that sit
    beside [model.parameters] (e.g. [[model.potential]], [model.static])

Adding a new strategy here means adding one assembler function and one
registry entry below — nothing about assemble_spec() itself changes,
same spirit as the strategy registry it mirrors.
"""
from __future__ import annotations

from typing import Any, Callable

Fragment = tuple[dict[str, Any], dict[str, Any]]  # (parameters_fragment, model_fragment)


# ── potential ─────────────────────────────────────────────────────────────────

def _potential_linear_regression(
    land_use_types: list[str], per_lu: dict[str, dict], global_: dict,
) -> Fragment:
    parameters = {"land_use_no_data": global_.get("land_use_no_data", "outros")}
    model = {
        "potential": [
            {"lu": lu, **per_lu.get(lu, {"const": 0.0, "betas": {}, "is_log": False})}
            for lu in land_use_types
        ]
    }
    return parameters, model


def _potential_precomputed(
    land_use_types: list[str], per_lu: dict[str, dict], global_: dict,
) -> Fragment:
    missing = [lu for lu in land_use_types if "suitability_column" not in per_lu.get(lu, {})]
    if missing:
        raise ValueError(f"potential_strategy='precomputed' missing suitability_column for: {missing}")
    parameters = {"potential_bias_step": global_.get("bias_step", 0.1)}
    model = {"potential_columns": {lu: per_lu[lu]["suitability_column"] for lu in land_use_types}}
    return parameters, model


POTENTIAL_BUILDERS: dict[str, Callable[[list[str], dict, dict], Fragment]] = {
    "linear_regression": _potential_linear_regression,
    "precomputed":       _potential_precomputed,
}


# ── allocation ────────────────────────────────────────────────────────────────

def _allocation_clue_like(
    land_use_types: list[str], per_lu: dict[str, dict], global_: dict,
) -> Fragment:
    if "complementar_lu" not in global_:
        raise ValueError("allocation_strategy='clue_like' requires complementar_lu")
    missing = [lu for lu in land_use_types if lu not in per_lu]
    if missing:
        raise ValueError(f"allocation_strategy='clue_like' missing per-land-use params for: {missing}")

    parameters = {
        "complementar_lu": global_["complementar_lu"],
        "cell_area":       global_.get("cell_area", 25.0),
    }
    model = {
        "static": {lu: per_lu[lu].get("static", -1) for lu in land_use_types},
        "allocation": [
            {"lu": lu, **{k: v for k, v in per_lu[lu].items() if k != "static"}}
            for lu in land_use_types
        ],
    }
    return parameters, model


ALLOCATION_BUILDERS: dict[str, Callable[[list[str], dict, dict], Fragment]] = {
    "clue_like": _allocation_clue_like,
}


# ── demand ────────────────────────────────────────────────────────────────────

def _demand_csv(land_use_types: list[str], global_: dict) -> Fragment:
    if not global_.get("demand_csv"):
        raise ValueError("demand_strategy='csv' requires demand_csv")
    return {"demand_csv": global_["demand_csv"]}, {}


def _demand_inline(land_use_types: list[str], global_: dict) -> Fragment:
    values = global_.get("values")
    if not values:
        raise ValueError("demand_strategy='inline' requires values")
    if any(len(row) != len(land_use_types) for row in values):
        raise ValueError(
            f"demand_strategy='inline': every row in values must have "
            f"{len(land_use_types)} columns (one per land use type), "
            f"in {land_use_types!r} order"
        )
    return {}, {"demand": {"values": values}}


DEMAND_BUILDERS: dict[str, Callable[[list[str], dict], Fragment]] = {
    "csv":    _demand_csv,
    "inline": _demand_inline,
}


# ── extension points, mirroring components.registry.register_* ────────────────

def register_potential_builder(name: str, builder: Callable[[list[str], dict, dict], Fragment]) -> None:
    POTENTIAL_BUILDERS[name] = builder


def register_allocation_builder(name: str, builder: Callable[[list[str], dict, dict], Fragment]) -> None:
    ALLOCATION_BUILDERS[name] = builder


def register_demand_builder(name: str, builder: Callable[[list[str], dict], Fragment]) -> None:
    DEMAND_BUILDERS[name] = builder


# ── top-level assembly ──────────────────────────────────────────────────────────

def assemble_spec(
    *,
    land_use_types: list[str],
    n_steps: int,
    potential_strategy: str,
    potential_per_lu: dict[str, dict],
    potential_global: dict,
    allocation_strategy: str,
    allocation_per_lu: dict[str, dict],
    allocation_global: dict,
    demand_strategy: str,
    demand_global: dict,
    driver_columns: list[str] | None = None,
    resolution: float | None = None,
) -> dict:
    """
    Build the full `{"model": {...}}` dict a TOML file for
    LUCCVectorExecutor / LUCCRasterExecutor would parse into.

    driver_columns: if omitted and potential_strategy == "linear_regression",
    it's derived automatically from the union of all betas keys across
    land use types — the common case, since driver columns are exactly
    the columns every regression coefficient refers to.
    """
    if land_use_types != sorted(set(land_use_types), key=land_use_types.index):
        raise ValueError("land_use_types must not contain duplicates")

    try:
        potential_builder = POTENTIAL_BUILDERS[potential_strategy]
    except KeyError as exc:
        raise ValueError(
            f"Unknown potential_strategy {potential_strategy!r}. "
            f"Registered: {sorted(POTENTIAL_BUILDERS)}"
        ) from exc
    try:
        allocation_builder = ALLOCATION_BUILDERS[allocation_strategy]
    except KeyError as exc:
        raise ValueError(
            f"Unknown allocation_strategy {allocation_strategy!r}. "
            f"Registered: {sorted(ALLOCATION_BUILDERS)}"
        ) from exc
    try:
        demand_builder = DEMAND_BUILDERS[demand_strategy]
    except KeyError as exc:
        raise ValueError(
            f"Unknown demand_strategy {demand_strategy!r}. "
            f"Registered: {sorted(DEMAND_BUILDERS)}"
        ) from exc

    parameters: dict[str, Any] = {
        "n_steps":             n_steps,
        "land_use_types":      land_use_types,
        "potential_strategy":  potential_strategy,
        "allocation_strategy": allocation_strategy,
        "demand_strategy":     demand_strategy,
    }
    if resolution is not None:
        parameters["resolution"] = resolution

    model: dict[str, Any] = {}

    pot_params, pot_model = potential_builder(land_use_types, potential_per_lu, potential_global)
    parameters.update(pot_params)
    model.update(pot_model)

    alloc_params, alloc_model = allocation_builder(land_use_types, allocation_per_lu, allocation_global)
    parameters.update(alloc_params)
    model.update(alloc_model)

    demand_params, demand_model = demand_builder(land_use_types, demand_global)
    parameters.update(demand_params)
    model.update(demand_model)

    if demand_strategy == "inline":
        n_rows = len(demand_global.get("values", []))
        if n_rows < n_steps:
            raise ValueError(
                f"demand_strategy='inline' has {n_rows} row(s) in values, but "
                f"n_steps={n_steps} — DemandPreComputedValues indexes annual_demand "
                f"by step and needs at least {n_steps} rows, or the run fails "
                f"mid-simulation with IndexError instead of failing here."
            )

    if driver_columns is None and potential_strategy == "linear_regression":
        driver_columns = sorted({
            col
            for lu in land_use_types
            for col in potential_per_lu.get(lu, {}).get("betas", {})
        })
    if driver_columns:
        model["driver_columns"] = {"cols": driver_columns}

    model["parameters"] = parameters
    return {"model": model}


def spec_to_toml_string(spec: dict) -> str:
    """Serialize an assemble_spec() result to a TOML string."""
    import tomli_w
    return tomli_w.dumps(spec)
