from __future__ import annotations

from dissmodel.executor     import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.io           import load_dataset, save_dataset
from dissmodel.io.convert   import vector_to_raster_backend


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

        attrs = {lu: 0.0 for lu in lu_types}
        attrs.update({col: 0.0 for col in driver_cols})

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
        """
        from dissmodel.core import Environment
        from dissluc import DemandPreComputedValues, load_demand_csv
        from dissluc.modules.raster.potential.linear  import PotentialLinearRegression
        from dissluc.modules.raster.allocation.clue   import AllocationClueLike
        from dissluc.modules.schemas import RegressionSpec, AllocationSpec

        spec     = record.resolved_spec.get("model", {})
        params   = record.parameters
        lu_types = spec.get("land_use_types", ["f", "d", "outros"])
        n_steps  = params.get("n_steps", 7)

        # data injected by execute_lifecycle — no I/O here
        backend = data

        # band-level validation (only possible after rasterization)
        _check_bands(backend, spec)

        # ── build models ──────────────────────────────────────────────────────
        env = Environment(end_time=n_steps - 1)

        demand = DemandPreComputedValues(
            annual_demand  = load_demand_csv(params["demand_csv"], lu_types),
            land_use_types = lu_types,
        )

        potential_data = [[
            RegressionSpec(
                const  = p["const"],
                betas  = p.get("betas", {}),
                is_log = p.get("is_log", False),
            )
            for p in spec.get("potential", [])
        ]]

        allocation_data = [[
            AllocationSpec(**{k: v for k, v in a.items() if k != "lu"})
            for a in spec.get("allocation", [])
        ]]

        potential = PotentialLinearRegression(
            backend          = backend,
            potential_data   = potential_data,
            demand           = demand,
            land_use_types   = lu_types,
            land_use_no_data = spec.get("land_use_no_data", "outros"),
        )

        AllocationClueLike(
            backend         = backend,
            demand          = demand,
            potential       = potential,
            land_use_types  = lu_types,
            static          = spec.get("static", {}),
            complementar_lu = spec.get("complementar_lu", lu_types[0]),
            cell_area       = spec.get("cell_area", 25.0),
            allocation_data = allocation_data,
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

        record.add_log(f"Running {n_steps} steps...")
        env.run()
        record.add_log("Simulation complete")
        return backend, {}

    def save(self, result, record: ExperimentRecord) -> ExperimentRecord:
        if isinstance(result, tuple):
            backend, meta = result
        else:
            backend, meta = result, {}

        uri      = record.output_path or "local_output.tif"
        checksum = save_dataset((backend, meta), uri)

        record.output_path   = uri
        record.output_sha256 = checksum
        record.status        = "completed"
        record.add_log(f"Saved to {uri}")
        return record


# ── helpers ───────────────────────────────────────────────────────────────────

def _check_bands(backend, spec: dict) -> None:
    """
    Verify expected bands are present after rasterization.
    Runs inside run() after a single load() — not in validate().
    """
    lu_types    = spec.get("land_use_types", [])
    driver_cols = spec.get("driver_columns", {}).get("cols", [])
    expected    = set(lu_types) | set(driver_cols)

    if not expected:
        return

    actual  = set(backend.arrays.keys()) - {"mask"}
    missing = expected - actual

    if missing:
        raise ValueError(
            f"Bands missing after rasterization: {missing}\n"
            f"Check column_map or driver_columns in model.toml."
        )


if __name__ == "__main__":
    run_cli(LUCCRasterExecutor)
