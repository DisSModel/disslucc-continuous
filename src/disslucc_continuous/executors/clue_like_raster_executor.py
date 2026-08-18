from __future__ import annotations

import os
from dissmodel.executor     import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.io           import load_dataset, save_dataset
from dissmodel.io.convert   import vector_to_raster_backend

from dissmodel.io._utils import read_text

from disslucc_continuous.common.utils import default_output_uri

class LUCCRasterExecutor(ModelExecutor):
    """
    Executor for LUCC raster simulations (C-CLUE).
    Equivalent to lab1_main_raster.py — works via CLI and platform API.

    Input contract
    --------------
    After load(), the RasterBackend exposes bands named after land_use_types
    and driver_columns from the model spec. Non-canonical column names are
    resolved via column_map before rasterization.
    """

    name = "lucc_raster"

    # ── public contract ───────────────────────────────────────────────────────

    def load(self, record: ExperimentRecord):
        spec        = record.resolved_spec.get("model", {})
        params      = record.parameters
        lu_types    = spec.get("land_use_types", ["f", "d", "outros"])
        driver_cols = spec.get("driver_columns", {}).get("cols", [])
        # potential_columns is generic across strategies (e.g. suitability
        # arrays for potential_strategy="precomputed"); rasterize it here
        # too since load() only runs once and strategy resolution happens
        # later in run(), after rasterization has already paid its cost.
        extra_cols  = set(spec.get("potential_columns", {}).values())

        attrs = {lu: 0.0 for lu in lu_types}
        attrs.update({col: 0.0 for col in driver_cols})
        attrs.update({col: 0.0 for col in extra_cols})

        gdf, checksum = load_dataset(record.source.uri)
        record.source.checksum = checksum

        if record.column_map:
            gdf = gdf.rename(columns={v: k for k, v in record.column_map.items()})

        backend = vector_to_raster_backend(
            source       = gdf,
            resolution   = params.get("resolution", 5000.0),
            attrs        = attrs,
            crs          = params.get("crs"),
            nodata_value = -1,
        )

        record.add_log(
            f"Rasterized: shape={backend.shape} "
            f"valid={int(backend.get('mask').sum()):,} cells"
        )
        return backend

    def validate(self, record: ExperimentRecord) -> None:
        """
        Stateless pre-flight checks on the record itself — no data loading.

        Verifies that column_map keys are consistent with the model spec.
        Band-level checks (missing bands after rasterization) run at the
        start of run() after a single load(), where the cost is already paid.
        The rasterization in load() is expensive — never run it twice.
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

    def run(self, data, record: ExperimentRecord):
        """
        Validate bands, then execute the LUCC simulation.

        `data` is the RasterBackend returned by load(), injected by the platform.
        No I/O happens here — rasterization is done once in load().

        Like the vector executor, this one resolves Potential/Allocation via
        `model.potential_strategy` / `model.allocation_strategy` in the spec
        instead of importing a concrete class — see
        `disslucc_continuous.components.registry`.
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
        # See the identical comment in clue_like_vector_executor.py — TOML's
        # [model.parameters] table doesn't get promoted into resolved_spec
        # by dissmodel's CLI loader; merge it here explicitly.
        spec     = {**record.resolved_spec.get("model", {}), **params}
        lu_types = spec.get("land_use_types", ["f", "d", "outros"])
        n_steps  = params.get("n_steps", 7)

        # data injected by execute_lifecycle — no I/O here
        backend = data

        potential_strategy_name  = spec.get("potential_strategy", DEFAULT_POTENTIAL_STRATEGY)
        allocation_strategy_name = spec.get("allocation_strategy", DEFAULT_ALLOCATION_STRATEGY)
        demand_strategy_name     = spec.get("demand_strategy", DEFAULT_DEMAND_STRATEGY)
        PotentialCls  = resolve_potential(potential_strategy_name, "raster")
        AllocationCls = resolve_allocation(allocation_strategy_name, "raster")
        DemandCls     = resolve_demand(demand_strategy_name, "raster")

        # band-level validation (only possible after rasterization)
        _check_bands(backend, spec, extra_required=_strategy_required_columns(PotentialCls, spec, lu_types))

        # ── build models ──────────────────────────────────────────────────────
        env = Environment(end_time=n_steps - 1)

        demand_csv_uri = params.get("demand_csv") if demand_strategy_name == "csv" else None
        demand_raw     = read_text(demand_csv_uri) if demand_csv_uri else None

        demand = DemandCls.from_spec(
            spec, land_use_types=lu_types, demand_raw=demand_raw,
        )

        potential = PotentialCls.from_spec(
            spec, demand=demand, land_use_types=lu_types, backend=backend,
        )

        AllocationCls.from_spec(
            spec, demand=demand, potential=potential, land_use_types=lu_types, backend=backend,
        )

        if params.get("interactive", False):
            from dissmodel.visualization import RasterMap
            RasterMap(
                backend    = backend,
                band       = lu_types[0],
                cmap       = "Greens",
                scheme     = "equal_interval",
                k          = 5,
                legend     = True,
                mask_band  = "mask",
                mask_value = 0,
            )

        record.add_log(
            f"potential_strategy={potential_strategy_name} "
            f"allocation_strategy={allocation_strategy_name} "
            f"demand_strategy={demand_strategy_name}"
        )
        record.add_log(f"Running {n_steps} steps...")
        env.run()
        record.add_log("Simulation complete")
        return backend, {}

    def save(self, result, record: ExperimentRecord) -> ExperimentRecord:
        if isinstance(result, tuple):
            backend, meta = result
        else:
            backend, meta = result, {}

        uri = (
            record.output_path
            or default_output_uri(record.experiment_id, ext="tif")
        )

        if not uri.startswith("s3://"):
            os.makedirs(os.path.dirname(os.path.abspath(uri)), exist_ok=True)

        checksum = save_dataset((backend, meta), uri)

        record.output_path   = uri
        record.output_sha256 = checksum
        record.status        = "completed"
        record.add_log(f"Saved to {uri}")
        return record


# ── helpers ───────────────────────────────────────────────────────────────────

def _strategy_required_columns(strategy_cls, spec: dict, lu_types: list[str]) -> set[str]:
    """
    Ask the chosen potential strategy for any bands it needs beyond
    land_use_types/driver_columns. Strategies that don't declare extra
    requirements simply don't implement this classmethod.
    """
    hook = getattr(strategy_cls, "required_columns", None)
    return set(hook(spec, lu_types)) if hook else set()


def _check_bands(backend, spec: dict, extra_required: set[str] | None = None) -> None:
    """
    Verify expected bands are present after rasterization.
    Runs inside run() after a single load() — not in validate().
    """
    lu_types    = spec.get("land_use_types", [])
    driver_cols = spec.get("driver_columns", {}).get("cols", [])
    expected    = set(lu_types) | set(driver_cols) | (extra_required or set())

    if not expected:
        return

    actual  = set(backend.arrays.keys()) - {"mask"}
    missing = expected - actual

    if missing:
        raise ValueError(
            f"Bands missing after rasterization: {missing}\n"
            f"Check column_map, driver_columns, or the fields required by "
            f"the chosen potential_strategy in model.toml."
        )


if __name__ == "__main__":
    run_cli(LUCCRasterExecutor)
