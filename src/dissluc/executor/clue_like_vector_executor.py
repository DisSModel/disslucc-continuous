from __future__ import annotations

import geopandas as gpd

from dissmodel.executor     import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.io           import load_dataset, save_dataset


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
        """
        from dissmodel.core import Environment
        from dissluc import DemandPreComputedValues, load_demand_csv
        from dissluc.modules.vector.potential.linear import PotentialLinearRegression
        from dissluc.modules.vector.allocation.clue  import AllocationClueLike
        from dissluc.modules.schemas import RegressionSpec, AllocationSpec

        spec     = record.resolved_spec.get("model", {})
        params   = record.parameters
        lu_types = spec.get("land_use_types", ["f", "d", "outros"])
        n_steps  = params.get("n_steps", 7)

        # data injected by execute_lifecycle — no I/O here
        gdf = data

        # column-level validation (only possible after load)
        _check_columns(gdf, spec)

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
            gdf              = gdf,
            potential_data   = potential_data,
            demand           = demand,
            land_use_types   = lu_types,
            land_use_no_data = spec.get("land_use_no_data", "outros"),
        )

        AllocationClueLike(
            gdf             = gdf,
            demand          = demand,
            potential       = potential,
            land_use_types  = lu_types,
            static          = spec.get("static", {}),
            complementar_lu = spec.get("complementar_lu", lu_types[0]),
            cell_area       = spec.get("cell_area", 25.0),
            allocation_data = allocation_data,
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

        record.add_log(f"Running {n_steps} steps...")
        env.run()
        record.add_log("Simulation complete")
        return gdf

    def save(self, result: gpd.GeoDataFrame, record: ExperimentRecord) -> ExperimentRecord:
        uri      = record.output_path or "local_output.gpkg"
        checksum = save_dataset(result, uri)

        record.output_path   = uri
        record.output_sha256 = checksum
        record.status        = "completed"
        record.add_log(f"Saved to {uri}")
        return record


# ── helpers ───────────────────────────────────────────────────────────────────

def _check_columns(gdf: gpd.GeoDataFrame, spec: dict) -> None:
    """
    Verify expected columns are present after column_map has been applied.
    Runs inside run() after a single load() — not in validate().
    """
    lu_types    = spec.get("land_use_types", [])
    driver_cols = spec.get("driver_columns", {}).get("cols", [])
    expected    = set(lu_types) | set(driver_cols)

    if not expected:
        return

    missing = expected - set(gdf.columns)

    if missing:
        raise ValueError(
            f"Columns missing after column_map: {missing}\n"
            f"Dataset columns: {sorted(gdf.columns)}\n"
            f"Check column_map or driver_columns in model.toml."
        )


if __name__ == "__main__":
    run_cli(LUCCVectorExecutor)
