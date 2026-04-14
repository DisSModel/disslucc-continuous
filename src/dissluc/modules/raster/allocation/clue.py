"""
dissluc/raster/allocation/clue.py
----------------------------------
Raster version of AllocationClueLike.
All cell operations are fully vectorized with NumPy — no per-cell loops.
"""
from __future__ import annotations
import numpy as np

from dissluc.modules.schemas import AllocationSpec
from dissmodel.geo import SyncRasterModel

class AllocationClueLike(SyncRasterModel):
    """
    Raster CLUE allocation (Verburg et al. 1999).

    Equivalent to the vector version but operates on RasterBackend arrays.
    All operations are vectorized — suitable for grids of any size.
    """

    def setup(
        self,
        backend,
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
        super().setup(backend)
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

        default = AllocationSpec()
        if allocation_data is None:
            self.allocation_data = [default for _ in range(len(land_use_types))]
        else:
            region0 = allocation_data[0] if isinstance(allocation_data[0], list) else allocation_data
            self.allocation_data = list(region0)

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
                    f"Allocation did not converge at step {step} (error={max_diff:.1f})"
                )

        self._apply_complementar()

    def _compute_change(self, elasticity: list[float]) -> None:
        mask = self._mask()

        for lu_idx, lu in enumerate(self.land_use_types):
            lu_dir  = self.demand.get_current_lu_direction(lu_idx)
            pot     = self.backend.get(lu + "_pot").astype(np.float32)
            past    = self.backend.get(lu + "_past").astype(np.float32)
            alloc   = self.allocation_data[lu_idx]
            lu_stat = self.static[lu]

            min_ch  = alloc.min_change
            max_ch  = alloc.max_change
            min_val = alloc.min_value
            max_val = alloc.max_value

            if lu_stat == 1:
                self.backend.arrays[lu] = np.where(mask, past, self.backend.get(lu))
                continue

            change = pot * elasticity[lu_idx]
            change = np.where(np.abs(change) >= min_ch, change, 0.0)
            sign   = np.sign(change)
            change = np.clip(np.abs(change), 0.0, max_ch) * sign

            if lu_stat == 0:
                new_val = past + change
            else:
                cond    = ((pot >= 0) & (lu_dir == 1)) | ((pot <= 0) & (lu_dir == -1))
                new_val = past + np.where(cond, change, 0.0)

            new_val = np.clip(new_val, 0.0, 1.0)

            below_min = new_val <= min_val
            new_val   = np.where(below_min,
                                 np.where(past >= min_val, min_val, past),
                                 new_val)
            above_max = new_val > max_val
            new_val   = np.where(above_max,
                                 np.where(past <= max_val, max_val, past),
                                 new_val)

            self.backend.arrays[lu] = np.where(mask, new_val, self.backend.get(lu))

    def _correct_cell_change(self) -> None:
        lus   = self.land_use_types
        TOL   = 0.005
        MAX_L = 25

        alloc_min = np.array([self.allocation_data[i].min_value for i in range(len(lus))])
        alloc_max = np.array([self.allocation_data[i].max_value for i in range(len(lus))])
        static    = np.array([self.static[lu] for lu in lus])

        mask      = self._mask()
        shape     = self.shape
        flat_mask = mask.ravel()

        flat      = lambda lu: self.backend.get(lu).ravel().astype(np.float32)
        originals = {lu: flat(lu) for lu in lus}
        vals      = np.stack([flat(lu)           for lu in lus], axis=1)
        pasts     = np.stack([flat(lu + "_past") for lu in lus], axis=1)

        for _ in range(MAX_L):
            totcov = vals.sum(axis=1, keepdims=True)
            needs  = (np.abs(totcov - 1.0) > TOL).ravel() & flat_mask
            if not needs.any():
                break

            is_static  = (static >= 1) | (vals <= alloc_min) | (vals >= alloc_max)
            static_sum = (vals * is_static).sum(axis=1, keepdims=True)
            free_sum   = (vals * ~is_static).sum(axis=1, keepdims=True)
            target     = 1.0 - static_sum
            excess     = free_sum - target

            diffs      = (vals - pasts) * ~is_static
            totchange  = np.abs(diffs).sum(axis=1, keepdims=True)

            needs_b = needs[:, None]

            with_change = (totchange > 0) & needs_b
            correction  = np.where(
                with_change,
                np.abs(diffs) * excess / np.where(totchange > 0, totchange, 1.0),
                0.0,
            )

            no_change = (totchange == 0) & needs_b & ~is_static
            scale     = np.where(
                no_change & (free_sum > 0),
                target / np.where(free_sum > 0, free_sum, 1.0),
                1.0,
            )

            new_vals = np.where(no_change, vals * scale, vals - correction)
            new_vals = np.where(is_static, vals, new_vals)
            vals     = np.clip(new_vals, 0.0, 1.0)

        for i, lu in enumerate(lus):
            self.backend.arrays[lu] = np.where(
                flat_mask,
                vals[:, i],
                originals[lu],
            ).reshape(shape)

    def _compare_to_demand(self, step: int, elasticity: list[float]) -> float:
        mask     = self._mask()
        max_diff = 0.0

        for lu_idx, lu in enumerate(self.land_use_types):
            area   = float(self.backend.get(lu)[mask].sum()) * self.cell_area
            demand = self.demand.get_current_lu_demand(lu_idx)
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

    def _apply_complementar(self) -> None:
        mask   = self._mask()
        lus    = self.land_use_types
        others = [lu for lu in lus if lu != self.complementar_lu]

        total = sum(self.backend.get(lu).astype(np.float32) for lu in others)
        comp  = np.clip(1.0 - total, 0.0, 1.0)

        comp_original = self.backend.get(self.complementar_lu).astype(np.float32)
        self.backend.arrays[self.complementar_lu] = np.where(
            mask, comp, comp_original
        )

        deficit = np.maximum(0.0, total - 1.0)
        if deficit.any():
            no_data  = getattr(self, "land_use_no_data", None)
            eligible = [lu for lu in others if lu != no_data]
            if eligible:
                stacked = np.stack(
                    [self.backend.get(lu).astype(np.float32) for lu in eligible],
                    axis=0,
                )
                biggest = np.argmax(stacked, axis=0)
                for i, lu in enumerate(eligible):
                    deficit_mask = (biggest == i) & (deficit > 0) & mask
                    self.backend.arrays[lu] = np.where(
                        deficit_mask,
                        np.maximum(0.0, self.backend.get(lu) - deficit),
                        self.backend.get(lu),
                    )
