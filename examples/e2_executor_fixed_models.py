"""
examples/e2_executor_fixed_models.py
=====================================
Level 2 of 3 — the executor pattern, but the models are still fixed.

Adds the ModelExecutor lifecycle (load/validate/run/save) and the CLI
(`run_cli`) on top of example 1 — so this can now run from the command
line, be picked up by the platform, and get column-map validation and
save-with-checksum for free. What it does NOT add yet is the strategy
registry: PotentialLinearRegression, AllocationClueLike, and
DemandPreComputedValues are imported and instantiated directly inside
run(), exactly like example 1 — just wrapped in the executor lifecycle
instead of a bare script. Regression coefficients and land use types
still come from a TOML spec (that part isn't the point of this level),
but *which Python classes* build the model is fixed in code, not
selected by name.

This is what LUCCVectorExecutor looked like before it grew a strategy
registry (see example 3) — the middle step between "TerraME .lua
script" and "generic executor that reads strategy names from TOML".

Run:
    cd examples
    python e2_executor_fixed_models.py run --toml model.toml --input data/input/csAC.zip
"""
from __future__ import annotations

import geopandas as gpd

from dissmodel.core import Environment
from dissmodel.executor import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.io import load_dataset, save_dataset
from dissmodel.io._utils import read_text

from disslucc_continuous.components.demand.precomputed import (
    DemandPreComputedValues,
    load_demand_csv,
)
from disslucc_continuous.components.potential.vector.linear import PotentialLinearRegression
from disslucc_continuous.components.allocation.vector.clue import AllocationClueLike
from disslucc_continuous.schemas.schemas import RegressionSpec, AllocationSpec


class FixedModelsExecutor(ModelExecutor):
    """LUCC vector executor with fixed models — no strategy registry."""

    name = "e2_fixed"

    def load(self, record: ExperimentRecord) -> gpd.GeoDataFrame:
        gdf, checksum = load_dataset(record.source.uri)
        record.source.checksum = checksum
        record.add_log(f"Loaded GDF: {len(gdf)} features")
        return gdf

    def run(self, data: gpd.GeoDataFrame, record: ExperimentRecord) -> gpd.GeoDataFrame:
        params   = record.parameters
        # [model.parameters] isn't promoted into resolved_spec by dissmodel's
        # CLI TOML loader — merge it explicitly (see the same fix and its
        # rationale in the production executors).
        spec     = {**record.resolved_spec.get("model", {}), **params}
        lu_types = spec.get("land_use_types", ["f", "d", "outros"])
        n_steps  = params.get("n_steps", 7)
        gdf      = data

        env = Environment(end_time=n_steps - 1)

        demand_raw = read_text(params["demand_csv"])
        demand = DemandPreComputedValues(
            annual_demand  = load_demand_csv(demand_raw, lu_types),
            land_use_types = lu_types,
        )

        # Fixed class — no registry, no potential_strategy spec key.
        potential_map  = {p.get("lu"): p for p in spec.get("potential", [])}
        potential_data = [[
            RegressionSpec(
                const  = potential_map[lu].get("const", 0.0),
                betas  = potential_map[lu].get("betas", {}),
                is_log = potential_map[lu].get("is_log", False),
            ) if lu in potential_map else RegressionSpec(const=0.0)
            for lu in lu_types
        ]]
        potential = PotentialLinearRegression(
            gdf              = gdf,
            demand           = demand,
            land_use_types   = lu_types,
            land_use_no_data = spec.get("land_use_no_data", "outros"),
            potential_data   = potential_data,
        )

        # Fixed class — no registry, no allocation_strategy spec key.
        allocation_map  = {a.get("lu"): a for a in spec.get("allocation", [])}
        allocation_data = [[
            AllocationSpec(**{k: v for k, v in allocation_map[lu].items() if k != "lu"})
            if lu in allocation_map else AllocationSpec()
            for lu in lu_types
        ]]
        AllocationClueLike(
            gdf             = gdf,
            demand          = demand,
            potential       = potential,
            land_use_types  = lu_types,
            static          = {lu: spec.get("static", {}).get(lu, -1) for lu in lu_types},
            complementar_lu = spec.get("complementar_lu", lu_types[0]),
            cell_area       = spec.get("cell_area", 25.0),
            allocation_data = allocation_data,
        )

        record.add_log(f"Running {n_steps} steps (fixed models)...")
        env.run()
        record.add_log("Simulation complete")
        return gdf

    def save(self, result: gpd.GeoDataFrame, record: ExperimentRecord) -> ExperimentRecord:
        uri = record.output_path or "e2_result.gpkg"
        checksum = save_dataset(result, uri)
        record.output_path   = uri
        record.output_sha256 = checksum
        record.status        = "completed"
        record.add_log(f"Saved to {uri}")
        return record


if __name__ == "__main__":
    run_cli(FixedModelsExecutor)
