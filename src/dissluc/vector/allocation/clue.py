from __future__ import annotations
import numpy as np
import pandas as pd

from dissluc.schemas import AllocationSpec
from dissmodel.geo import SyncSpatialModel

class AllocationClueLike(SyncSpatialModel):
    """
    Alocação contínua tipo CLUE (Verburg et al. 1999).

    _past é gerenciado pelo LUCSpatialModel via synchronize()
    após cada execute() — equivale ao cs:synchronize() do TerraME.

    Esta versão é equivalente ao AllocationCClueLike.lua, incluindo:
      - correctCellChange: corrige células cuja soma de usos ≠ 1.0
      - minChange / maxChange por uso do solo
      - static == 0 (modo ANAP: muda independente da direção da demanda)
      - minValue / maxValue com lógica condicional de past
    """

    def setup(
        self,
        demand,
        potential,
        land_use_types:     list[str],
        static:             dict[str, int],
        complementar_lu:    str,
        cell_area:          float,
        max_difference:     float = 1643,
        max_iteration:      int   = 1000,
        initial_elasticity: float = 0.1,
        min_elasticity:     float = 0.001,
        max_elasticity:     float = 1.5,
        allocation_data:    list | None = None,
    ) -> None:
        self.demand             = demand
        self.potential          = potential
        self.land_use_types     = land_use_types
        self.static             = static
        self.complementar_lu    = complementar_lu
        self.cell_area          = cell_area
        self.max_difference     = max_difference
        self.max_iteration      = max_iteration
        self.initial_elasticity = initial_elasticity
        self.min_elasticity     = min_elasticity
        self.max_elasticity     = max_elasticity

        # allocation_data: list[list[AllocationSpec]] — regiões × usos
        # For now we use only region 1 (index 0), matching the Lua single-region default.
        # Shape: [[spec_lu0, spec_lu1, ...], [region2...], ...]
        default = AllocationSpec()
        if allocation_data is None:
            self.allocation_data = [default for _ in range(len(land_use_types))]
        else:
            # flatten: take region 0
            region0 = allocation_data[0] if isinstance(allocation_data[0], list) else allocation_data
            self.allocation_data = list(region0)

    # ── main loop ─────────────────────────────────────────────────────────────

    def execute(self) -> None:
        step       = int(self.env.now())
        elasticity = [self.initial_elasticity] * len(self.land_use_types)
        n_iter     = 0
        max_adjust = self.max_difference
        flag_flex  = False

        while True:
            if step != 0:
                self._compute_change(elasticity)
                self._correct_cell_change()

            max_diff = self._compare_to_demand(step, elasticity)
            if max_diff <= max_adjust:
                break

            n_iter += 1
            if n_iter > self.max_iteration * 0.5 and not flag_flex:
                max_adjust *= 2
                flag_flex   = True
            if n_iter >= self.max_iteration:
                raise RuntimeError(
                    f"Alocação não convergiu no passo {step} (erro={max_diff:.1f})"
                )

        self._apply_complementar()

    # ── compute change ────────────────────────────────────────────────────────

    def _compute_change(self, elasticity: list[float]) -> None:
        """
        Equivalent to AllocationCClueLike.computeChange in Lua.
        Applies minChange, maxChange, static==0, minValue, maxValue with past logic.
        """
        for lu_idx, lu in enumerate(self.land_use_types):
            lu_dir  = self.demand.get_current_lu_direction(lu_idx)
            pot     = self.gdf[lu + "_pot"]
            past    = self.gdf[lu + "_past"]
            alloc   = self.allocation_data[lu_idx]
            lu_stat = self.static[lu]

            min_ch  = alloc.min_change
            max_ch  = alloc.max_change
            min_val = alloc.min_value
            max_val = alloc.max_value

            if lu_stat == 1:
                # fixed — restore past
                self.gdf[lu] = past.copy()
                continue

            # raw change
            change = pot * elasticity[lu_idx]

            # apply minChange: if |change| < minChange, zero out
            change = change.where(change.abs() >= min_ch, 0.0)

            # apply maxChange: cap magnitude, preserve sign
            sign   = np.sign(change)
            change = change.abs().clip(upper=max_ch) * sign

            if lu_stat == 0:
                # ANAP mode: change regardless of demand direction
                new_val = past + change
            else:
                # lu_stat == -1: change only in demand direction
                cond    = ((pot >= 0) & (lu_dir == 1)) | ((pot <= 0) & (lu_dir == -1))
                new_val = past + change.where(cond, 0.0)

            # global clip [0, 1]
            new_val = new_val.clip(0.0, 1.0)

            # minValue with past logic:
            # if new < minValue AND past >= minValue → set to minValue
            # if new < minValue AND past < minValue  → restore past
            below_min = new_val <= min_val
            new_val   = new_val.where(
                ~below_min,
                np.where(past >= min_val, min_val, past),
            )

            # maxValue with past logic:
            # if new > maxValue AND past <= maxValue → set to maxValue
            # if new > maxValue AND past > maxValue  → restore past
            above_max = new_val > max_val
            new_val   = new_val.where(
                ~above_max,
                np.where(past <= max_val, max_val, past),
            )

            self.gdf[lu] = new_val

    # ── correct cell change ───────────────────────────────────────────────────

    def _correct_cell_change(self) -> None:
        """
        Vectorized translation of AllocationCClueLike.correctCellChange (Lua).

        Ensures each cell's land-use values sum to 1.0 (±0.005 tolerance).
        Uses pandas/numpy instead of cell-by-cell loops for performance.
        """
        lus  = self.land_use_types
        TOL  = 0.005
        MAX_L = 25

        vals  = self.gdf[lus].copy()
        pasts = self.gdf[[lu + "_past" for lu in lus]].copy()
        pasts.columns = lus   # align column names

        alloc_min = np.array([self.allocation_data[i].min_value for i in range(len(lus))])
        alloc_max = np.array([self.allocation_data[i].max_value for i in range(len(lus))])
        static    = np.array([self.static[lu]                   for lu in lus])

        # ── iterative correction loop ─────────────────────────────────────
        for _ in range(MAX_L):
            totcov = vals.sum(axis=1)
            needs  = (totcov - 1.0).abs() > TOL
            if not needs.any():
                break

            # which LUs are "static" per cell: static==1 or at min/max boundary
            is_static = (
                (static >= 1)
                | (vals.values <= alloc_min)
                | (vals.values >= alloc_max)
            )  # shape: (n_cells, n_lu)

            static_sum = (vals.values * is_static).sum(axis=1, keepdims=True)
            free_sum   = (vals.values * ~is_static).sum(axis=1, keepdims=True)
            target     = 1.0 - static_sum   # what the free LUs should sum to

            excess    = free_sum - target    # positive = too much, negative = too little
            diffs     = (vals.values - pasts.values) * ~is_static
            totchange = np.abs(diffs).sum(axis=1, keepdims=True)

            # cells where totchange > 0: redistribute proportionally to |change|
            with_change = (totchange > 0) & needs.values[:, None]
            correction  = np.where(
                with_change,
                np.abs(diffs) * excess / np.where(totchange > 0, totchange, 1.0),
                0.0,
            )
            # cells where totchange == 0: rescale proportionally to value
            no_change = (totchange == 0) & needs.values[:, None] & ~is_static
            scale     = np.where(
                no_change & (free_sum > 0),
                target / np.where(free_sum > 0, free_sum, 1.0),
                1.0,
            )

            new_vals = np.where(
                no_change,
                vals.values * scale,
                vals.values - correction,
            )
            new_vals = np.where(is_static, vals.values, new_vals)
            new_vals = np.clip(new_vals, 0.0, 1.0)
            vals     = pd.DataFrame(new_vals, index=vals.index, columns=lus)

        self.gdf[lus] = vals

    # ── compare to demand ─────────────────────────────────────────────────────

    def _compare_to_demand(self, step: int, elasticity: list[float]) -> float:
        areas    = [self.gdf[lu].sum() * self.cell_area for lu in self.land_use_types]
        max_diff = 0.0

        for lu_idx, lu in enumerate(self.land_use_types):
            demand = self.demand.get_current_lu_demand(lu_idx)
            area   = areas[lu_idx]
            lu_dir = self.demand.get_current_lu_direction(lu_idx)

            if area == 0:
                continue
            if lu_dir == 0 and step == 0:
                lu_dir = 1 if demand >= area else -1

            elasticity[lu_idx] *= demand / area if lu_dir == 1 else area / demand

            if elasticity[lu_idx] > self.max_elasticity:
                elasticity[lu_idx] = self.max_elasticity
                self.potential.modify(1, lu_idx, lu_dir)
            elif elasticity[lu_idx] < self.min_elasticity:
                if self.static[lu] < 0:
                    elasticity[lu_idx] = self.min_elasticity
                    self.potential.modify(1, lu_idx, -lu_dir)
                else:
                    self.demand.change_lu_direction(lu_idx)

            max_diff = max(max_diff, abs(area - demand))

        return max_diff

    # ── apply complementar ────────────────────────────────────────────────────

    def _apply_complementar(self) -> None:
        """
        Equivalent to the final forEachCell block in AllocationCClueLike.lua.
        Sets complementarLU = 1 - sum(others).
        If result < 0, subtracts the deficit from the LU with the largest value.
        """
        lus    = self.land_use_types
        others = [lu for lu in lus if lu != self.complementar_lu]
        no_data = getattr(self, "land_use_no_data", None)

        total = self.gdf[others].sum(axis=1)
        comp  = 1.0 - total
        needs_fix = comp < 0

        self.gdf[self.complementar_lu] = comp.clip(lower=0.0)

        # for cells where complementar < 0, subtract from the biggest non-nodata LU
        if needs_fix.any():
            eligible = [lu for lu in others if lu != no_data]
            if eligible:
                biggest_lu  = self.gdf.loc[needs_fix, eligible].idxmax(axis=1)
                deficit     = -comp[needs_fix]
                for idx in self.gdf.index[needs_fix]:
                    bl = biggest_lu[idx]
                    self.gdf.at[idx, bl] = max(0.0, self.gdf.at[idx, bl] - deficit[idx])
