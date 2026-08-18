"""
tests/test_potential_pluggability.py
=====================================
Proves that AllocationClueLike is decoupled from PotentialLinearRegression:
it only depends on PotentialProtocol (get_potential + modify). This test
swaps in PotentialPrecomputed — a strategy with completely different
internals (no regression, no betas, a static suitability column read
straight from the gdf/backend) — and runs the exact same Allocation
class unmodified, for both the vector and raster substrates.

If this test breaks because Allocation started reaching into a
concrete Potential attribute (e.g. `potential.potential_data`) or into
the `<lu>_pot` column/array directly instead of calling
`potential.get_potential(lu)`, that is a coupling regression.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from dissmodel.core import Environment
from disslucc_continuous import DemandPreComputedValues
from disslucc_continuous.components.allocation.vector import AllocationClueLike as AllocVector
from disslucc_continuous.components.allocation.raster import AllocationClueLike as AllocRaster
from disslucc_continuous.components.potential.vector import PotentialPrecomputed as PotVector
from disslucc_continuous.components.potential.raster import PotentialPrecomputed as PotRaster

LU_TYPES = ["f", "d", "outros"]
N_STEPS = 4


def _demand():
    # Demanda simples e crescente para "d", decrescente para "f".
    annual = [
        [70.0, 20.0, 10.0],
        [65.0, 25.0, 10.0],
        [60.0, 30.0, 10.0],
        [55.0, 35.0, 10.0],
    ]
    return DemandPreComputedValues(annual_demand=annual, land_use_types=LU_TYPES)


def test_vector_allocation_runs_with_precomputed_potential():
    n = 20
    rng = np.random.default_rng(0)
    gdf = gpd.GeoDataFrame(
        {
            "f":       [0.7] * n,
            "d":       [0.2] * n,
            "outros":  [0.1] * n,
            "suit_f":  rng.uniform(0.0, 1.0, n),
            "suit_d":  rng.uniform(0.0, 1.0, n),
            "suit_outros": rng.uniform(0.0, 1.0, n),
            "geometry": [Point(i, 0) for i in range(n)],
        }
    )

    env = Environment(end_time=N_STEPS - 1)
    demand = _demand()
    potential = PotVector(
        gdf=gdf,
        suitability_columns={"f": "suit_f", "d": "suit_d", "outros": "suit_outros"},
        land_use_types=LU_TYPES,
    )
    AllocVector(
        gdf=gdf,
        demand=demand,
        potential=potential,
        land_use_types=LU_TYPES,
        static={"f": -1, "d": -1, "outros": 0},
        complementar_lu="outros",
        cell_area=25.0,
    )
    env.run()

    totals = gdf[LU_TYPES].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=0.01)
    assert (gdf[LU_TYPES] >= -1e-9).all().all()


def test_raster_allocation_runs_with_precomputed_potential():
    from dissmodel.geo.raster.backend import RasterBackend

    shape = (5, 5)
    rng = np.random.default_rng(1)
    backend = RasterBackend(shape=shape)
    backend.set("f",      np.full(shape, 0.7, dtype=np.float32))
    backend.set("d",      np.full(shape, 0.2, dtype=np.float32))
    backend.set("outros", np.full(shape, 0.1, dtype=np.float32))
    backend.set("suit_f", rng.uniform(0.0, 1.0, shape).astype(np.float32))
    backend.set("suit_d", rng.uniform(0.0, 1.0, shape).astype(np.float32))
    backend.set("suit_outros", rng.uniform(0.0, 1.0, shape).astype(np.float32))

    env = Environment(end_time=N_STEPS - 1)
    demand = _demand()
    potential = PotRaster(
        backend=backend,
        suitability_arrays={"f": "suit_f", "d": "suit_d", "outros": "suit_outros"},
        land_use_types=LU_TYPES,
    )
    AllocRaster(
        backend=backend,
        demand=demand,
        potential=potential,
        land_use_types=LU_TYPES,
        static={"f": -1, "d": -1, "outros": 0},
        complementar_lu="outros",
        cell_area=25.0,
    )
    env.run()

    totals = sum(backend.get(lu).astype(np.float64) for lu in LU_TYPES)
    assert np.allclose(totals, 1.0, atol=0.01)
