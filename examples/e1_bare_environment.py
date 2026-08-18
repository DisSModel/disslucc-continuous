"""
examples/e1_bare_environment.py
=====================================
Level 1 of 3 — no executor pattern at all.

This is the closest thing to a TerraME/LuccME .lua script: direct
imports of concrete classes, hardcoded parameters, models instantiated
straight into an Environment, then env.run(). No ModelExecutor, no
load()/validate()/run()/save() lifecycle, no CLI plumbing, no strategy
registry — just "build the objects, run them", the way LuccMEModel{...}
callers used to.

    D1 = Demand{...}
    P1 = PotentialCLinearRegression{...}
    A1 = AllocationCClueLike{...}
    Lab1 = LuccMEModel{demand=D1, potential=P1, allocation=A1, ...}
    Lab1:run(7)

becomes, in DisSModel:

    Environment(...)
    demand    = DemandPreComputedValues(...)   # connects to env on creation
    potential = PotentialLinearRegression(...) # connects to env on creation
    AllocationClueLike(...)                    # connects to env on creation
    env.run()

Run directly:
    python examples/e1_bare_environment.py
"""
from __future__ import annotations

from pathlib import Path

from dissmodel.core import Environment
from dissmodel.io import load_dataset
from dissmodel.io._utils import read_text

from disslucc_continuous.components.demand.precomputed import (
    DemandPreComputedValues,
    load_demand_csv,
)
from disslucc_continuous.components.potential.vector.linear import PotentialLinearRegression
from disslucc_continuous.components.allocation.vector.clue import AllocationClueLike
from disslucc_continuous.schemas.schemas import RegressionSpec, AllocationSpec

DATA_DIR = Path(__file__).resolve().parent / "data" / "input"

# ---------------------------------------------------------------------------
# Hardcoded parameters — the Python-literal equivalent of a .lua script's
# constants. No TOML, no spec dict, no CLI args.
# ---------------------------------------------------------------------------
LAND_USE_TYPES   = ["f", "d", "outros"]
LAND_USE_NO_DATA = "outros"
COMPLEMENTAR_LU  = "f"
CELL_AREA        = 25.0
N_STEPS          = 7

# ---------------------------------------------------------------------------
# Load data — no lifecycle abstraction, just call the loaders directly.
# Path is resolved relative to this script, so it runs the same way
# regardless of the current working directory it's launched from.
# ---------------------------------------------------------------------------
gdf, _checksum = load_dataset(str(DATA_DIR / "csAC.zip"))
demand_raw     = read_text(str(DATA_DIR / "examples_demand_lab1.csv"))

# ---------------------------------------------------------------------------
# Environment — must exist before any Model is instantiated.
# ---------------------------------------------------------------------------
env = Environment(end_time=N_STEPS - 1)

# ---------------------------------------------------------------------------
# Models — each one connects itself to the active Environment on
# creation (TerraME's cs:add() equivalent, done implicitly by Model.__init__).
# ---------------------------------------------------------------------------
demand = DemandPreComputedValues(
    annual_demand  = load_demand_csv(demand_raw, LAND_USE_TYPES),
    land_use_types = LAND_USE_TYPES,
)

potential = PotentialLinearRegression(
    gdf              = gdf,
    demand           = demand,
    land_use_types   = LAND_USE_TYPES,
    land_use_no_data = LAND_USE_NO_DATA,
    potential_data   = [[
        RegressionSpec(
            const=0.7392,
            betas={
                "assentamen": -0.2193, "uc_us": 0.1754, "uc_pi": 0.09708,
                "ti": 0.1207, "dist_riobr": 0.0000002388, "fertilidad": -0.1313,
            },
        ),
        RegressionSpec(
            const=0.267,
            betas={
                "rodovias": -0.0000009922, "assentamen": 0.2294,
                "uc_us": -0.09867, "dist_riobr": -0.0000003216, "fertilidad": 0.1281,
            },
        ),
        RegressionSpec(const=0.0),  # outros
    ]],
)

AllocationClueLike(
    gdf             = gdf,
    demand          = demand,
    potential       = potential,
    land_use_types  = LAND_USE_TYPES,
    static          = {"f": -1, "d": -1, "outros": 1},
    complementar_lu = COMPLEMENTAR_LU,
    cell_area       = CELL_AREA,
    allocation_data = [[
        AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
        AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
        AllocationSpec(static=1,  min_value=0, max_value=1, min_change=0, max_change=1),
    ]],
)

# ---------------------------------------------------------------------------
# Run.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Running {N_STEPS} steps over {len(gdf)} cells...")
    env.run()
    print(gdf[LAND_USE_TYPES].describe())
    out_path = Path(__file__).resolve().parent / "e1_result.gpkg"
    gdf.to_file(out_path, driver="GPKG")
    print(f"Saved {out_path}")
