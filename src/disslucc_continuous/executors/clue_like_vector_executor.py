from __future__ import annotations

import os
import geopandas as gpd

from dissmodel.executor     import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.io           import load_dataset, save_dataset

from disslucc_continuous.common.utils import default_output_uri
from dissmodel.io._utils import read_text

class LUCCVectorExecutor(ModelExecutor):
    """
    Executor for LUCC vector simulations (C-CLUE / GeoDataFrame).
    Equivalent to lab1_main.py — works via CLI and platform API.

    Input contract
    --------------
    After load(), the GeoDataFrame exposes columns named after land_use_types
    and driver_columns from the model spec. Non-canonical column names are
    resolved via column_map before any model sees the data.
    """

    name = "lucc_vector"

    # ── public contract ───────────────────────────────────────────────────────

    def load(self, record: ExperimentRecord) -> gpd.GeoDataFrame:
        gdf, checksum = load_dataset(record.source.uri)
        record.source.checksum = checksum

        if record.column_map:
            gdf = gdf.rename(columns={v: k for k, v in record.column_map.items()})

        record.add_log(f"Loaded GDF: {len(gdf)} features  crs={gdf.crs}")
        return gdf

    def validate(self, record: ExperimentRecord) -> None:
        """
        Stateless pre-flight checks on the record itself — no data loading.

        Verifies that column_map keys are consistent with the model spec.
        Column-level checks (missing columns after mapping) run at the start
        of run() after a single load(), where the cost is already paid.
        """
        spec        = record.resolved_spec.get("model", {})
        lu_types    = spec.get("land_use_types", [])
        driver_cols = spec.get("driver_columns", {}).get("cols", [])
        expected    = set(lu_types) | set(driver_cols)

        if not expected:
            return

        if record.column_map:
            unknown = set(record.column_map) - expected
            if unknown:
                raise ValueError(
                    f"column_map references columns not in model spec: {unknown}\n"
                    f"Expected keys from spec: {expected}"
                )

    def run(self, data: gpd.GeoDataFrame, record: ExperimentRecord) -> gpd.GeoDataFrame:
        """
        Validate columns, then execute the LUCC simulation.

        `data` is the GeoDataFrame returned by load(), injected by the platform.
        No I/O happens here.

        This executor does not import or know about any concrete Potential
        or Allocation class. `model.potential_strategy` / `model.allocation_strategy`
        in the spec select which registered strategy to build via its own
        `from_spec` factory (see `disslucc_continuous.components.registry`) —
        equivalent to a modeler swapping which `Potential*.lua` / `Allocation*.lua`
        they pass into `LuccMEModel{...}` in the original LuccME.
        """
        from dissmodel.core import Environment
        from disslucc_continuous.components.registry import (
            resolve_potential,
            resolve_allocation,
            resolve_demand,
            DEFAULT_POTENTIAL_STRATEGY,
            DEFAULT_ALLOCATION_STRATEGY,
            DEFAULT_DEMAND_STRATEGY,
        )

        params   = record.parameters
        # [model.parameters] (record.parameters) lands separately from the
        # rest of [model.*] in resolved_spec — dissmodel's CLI TOML loader
        # does not promote it up. Merge it here so land_use_types,
        # complementar_lu, potential_strategy, etc. declared under
        # [model.parameters] are actually seen by the spec.get(...) calls
        # below, instead of silently falling back to defaults. `params`
        # wins the merge so CLI --param overrides (already folded into
        # record.parameters by _build_record) still take precedence.
        spec     = {**record.resolved_spec.get("model", {}), **params}
        lu_types = spec.get("land_use_types", ["f", "d", "outros"])
        n_steps  = params.get("n_steps", 7)

        # data injected by execute_lifecycle — no I/O here
        gdf = data

        potential_strategy_name  = spec.get("potential_strategy", DEFAULT_POTENTIAL_STRATEGY)
        allocation_strategy_name = spec.get("allocation_strategy", DEFAULT_ALLOCATION_STRATEGY)
        demand_strategy_name     = spec.get("demand_strategy", DEFAULT_DEMAND_STRATEGY)
        PotentialCls  = resolve_potential(potential_strategy_name, "vector")
        AllocationCls = resolve_allocation(allocation_strategy_name, "vector")
        DemandCls     = resolve_demand(demand_strategy_name, "vector")

        # column-level validation (only possible after load) — merges the
        # base contract (land_use_types + driver_columns) with whatever
        # extra columns the chosen potential strategy declares as required.
        _check_columns(gdf, spec, extra_required=_strategy_required_columns(PotentialCls, spec, lu_types))

        # ── build models ──────────────────────────────────────────────────────
        env = Environment(end_time=n_steps - 1)

        # Read demand_csv here (once, if a strategy needs it) — from_spec
        # itself does no I/O, same convention as the potential/allocation
        # factories. Strategies that don't need it (e.g. "inline") simply
        # ignore demand_raw via **_ignored.
        # Only read demand_csv when the selected strategy is "csv" — a
        # leftover/unused demand_csv key alongside demand_strategy="inline"
        # (or any future strategy that doesn't need a CSV) must not trigger
        # a file read that then fails or silently succeeds on stale data.
        demand_csv_uri = params.get("demand_csv") if demand_strategy_name == "csv" else None
        demand_raw     = read_text(demand_csv_uri) if demand_csv_uri else None

        demand = DemandCls.from_spec(
            spec, land_use_types=lu_types, demand_raw=demand_raw,
        )

        potential = PotentialCls.from_spec(
            spec, demand=demand, land_use_types=lu_types, gdf=gdf,
        )

        AllocationCls.from_spec(
            spec, demand=demand, potential=potential, land_use_types=lu_types, gdf=gdf,
        )

        if params.get("interactive", False):
            from dissmodel.visualization import Map
            Map(
                gdf         = gdf,
                plot_params = {
                    "column": lu_types[0],
                    "cmap":   "Greens",
                    "scheme": "equal_interval",
                    "k":      5,
                    "legend": True,
                },
            )

        record.add_log(
            f"potential_strategy={potential_strategy_name} "
            f"allocation_strategy={allocation_strategy_name} "
            f"demand_strategy={demand_strategy_name}"
        )
        record.add_log(f"Running {n_steps} steps...")
        env.run()
        record.add_log("Simulation complete")
        return gdf

    def save(self, result: gpd.GeoDataFrame, record: ExperimentRecord) -> ExperimentRecord:
        uri = (
            record.output_path
            or default_output_uri(record.experiment_id, ext="gpkg")
        )
        
        if not uri.startswith("s3://"):
            os.makedirs(os.path.dirname(os.path.abspath(uri)), exist_ok=True)

        checksum = save_dataset(result, uri)

        record.output_path   = uri
        record.output_sha256 = checksum
        record.status        = "completed"
        record.add_log(f"Saved to {uri}")
        return record


# ── helpers ───────────────────────────────────────────────────────────────────


    
def _strategy_required_columns(strategy_cls, spec: dict, lu_types: list[str]) -> set[str]:
    """
    Ask the chosen potential strategy for any columns it needs beyond
    land_use_types/driver_columns (e.g. potential_columns for
    PotentialPrecomputed). Strategies that don't declare extra
    requirements (e.g. PotentialLinearRegression) simply don't
    implement this classmethod.
    """
    hook = getattr(strategy_cls, "required_columns", None)
    return set(hook(spec, lu_types)) if hook else set()


def _check_columns(gdf: gpd.GeoDataFrame, spec: dict, extra_required: set[str] | None = None) -> None:
    """
    Verify expected columns are present after column_map has been applied.
    Runs inside run() after a single load() — not in validate().
    """
    lu_types    = spec.get("land_use_types", [])
    driver_cols = spec.get("driver_columns", {}).get("cols", [])
    expected    = set(lu_types) | set(driver_cols) | (extra_required or set())

    if not expected:
        return

    missing = expected - set(gdf.columns)

    if missing:
        raise ValueError(
            f"Columns missing after column_map: {missing}\n"
            f"Dataset columns: {sorted(gdf.columns)}\n"
            f"Check column_map, driver_columns, or the fields required by "
            f"the chosen potential_strategy in model.toml."
        )


if __name__ == "__main__":
    run_cli(LUCCVectorExecutor)
