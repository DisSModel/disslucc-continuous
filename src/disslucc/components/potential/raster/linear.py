"""
dissluc/raster/potential/linear.py
----------------------------------
Raster version of PotentialLinearRegression.
Operates on RasterBackend arrays instead of GeoDataFrame columns.
"""
from __future__ import annotations
import math
import numpy as np

from disslucc.common.schemas import RegressionSpec

from dissmodel.geo import SyncRasterModel

class PotentialLinearRegression(SyncRasterModel):
    """
    Raster potential via linear regression (Verburg et al. 1999).

    All driver and LU arrays must be pre-loaded into the RasterBackend.
    Array names must match the beta keys in RegressionSpec.betas.
    """

    def setup(
        self,
        backend,
        potential_data:   list[list[RegressionSpec]],
        demand,
        land_use_types:   list[str],
        land_use_no_data: str | None = None,
        region_attr:      str = "region",
    ) -> None:
        super().setup(backend)
        self.potential_data   = potential_data
        self.demand           = demand
        self.land_use_types   = land_use_types
        self.land_use_no_data = land_use_no_data
        self.region_attr      = region_attr

        # ensure region array exists — default all cells to region 1
        if region_attr not in self.backend.arrays:
            self.backend.set(region_attr, np.ones(self.shape, dtype=np.int32))

        # initialise newconst and _pot arrays
        for region in self.potential_data:
            for spec in region:
                spec.newconst = spec.const

        for lu in self.land_use_types:
            self.backend.set(lu + "_pot", np.zeros(self.shape, dtype=np.float32))

    def execute(self) -> None:
        step = int(self.env.now())
        for r_idx, region in enumerate(self.potential_data):
            r_number = r_idx + 1
            for spec in region:
                spec.newconst = spec.const
            if step > 0:
                self._adapt_constants(r_number)
            for lu_idx in range(len(self.land_use_types)):
                self._compute_potential(r_number, lu_idx)

    def _adapt_constants(self, r_number: int) -> None:
        for lu_idx, spec in enumerate(self.potential_data[r_number - 1]):
            curr = self.demand.get_current_lu_demand(lu_idx)
            prev = self.demand.get_previous_lu_demand(lu_idx)
            if prev == 0:
                continue
            plus = (curr - prev) / prev
            if spec.is_log:
                if plus > 0:   spec.newconst -= math.log10(plus) * 0.01
                elif plus < 0: spec.newconst += math.log10(-plus) * 0.01
            else:
                spec.newconst += plus * 0.01

    def _compute_potential(self, r_number: int, lu_idx: int) -> None:
        lu   = self.land_use_types[lu_idx]
        spec = self.potential_data[r_number - 1][lu_idx]
        mask = self.backend.get(self.region_attr) == r_number  # bool 2D

        reg = np.full(self.shape, spec.newconst, dtype=np.float32)
        for col, beta in spec.betas.items():
            reg += beta * self.backend.get(col).astype(np.float32)

        if spec.is_log:
            reg = 10.0 ** reg
        reg = np.clip(reg, 0.0, 1.0)

        if self.land_use_no_data:
            no_data_arr = self.backend.get(self.land_use_no_data).astype(np.float32)
            reg = reg * (1.0 - no_data_arr)

        lu_past = self.backend.get(lu + "_past").astype(np.float32)
        pot     = self.backend.arrays[lu + "_pot"].copy()
        pot     = np.where(mask, reg - lu_past, pot)
        self.backend.arrays[lu + "_pot"] = pot

    def modify(self, r_number: int, lu_idx: int, direction: int) -> None:
        spec = self.potential_data[r_number - 1][lu_idx]
        if spec.is_log:
            spec.newconst -= math.log10(0.1) * direction
        else:
            spec.newconst += 0.1 * direction
        self._compute_potential(r_number, lu_idx)
