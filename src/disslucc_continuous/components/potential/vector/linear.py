from __future__ import annotations
import math

from disslucc_continuous.schemas.schemas import RegressionSpec

from dissmodel.geo import SyncSpatialModel

class PotentialLinearRegression(SyncSpatialModel):
    """
    Potencial de mudança por regressão linear contínua (CLUE).
    Verburg et al. (1999).
    """

    def setup(
        self,
        potential_data:   list[list[RegressionSpec]],
        demand,
        land_use_types:   list[str],
        land_use_no_data: str | None = None,
        region_attr:      str = "region",
    ) -> None:
        self.potential_data   = potential_data
        self.demand           = demand
        self.land_use_types   = land_use_types
        self.land_use_no_data = land_use_no_data
        self.region_attr      = region_attr

        if self.region_attr not in self.gdf.columns:
            self.gdf[self.region_attr] = 1

        for region in self.potential_data:
            for spec in region:
                spec.newconst = spec.const

        for lu in self.land_use_types:
            self.gdf[lu + "_pot"] = 0.0
        # _past: criado e gerenciado pelo Allocation via synchronize()

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
        mask = self.gdf[self.region_attr] == r_number

        reg = self.gdf.loc[mask, self.land_use_types[0]] * 0.0 + spec.newconst
        for col, beta in spec.betas.items():
            reg = reg + beta * self.gdf.loc[mask, col]

        if spec.is_log:
            reg = 10 ** reg
        reg = reg.clip(0, 1)
        if self.land_use_no_data:
            reg = reg * (1.0 - self.gdf.loc[mask, self.land_use_no_data])

        self.gdf.loc[mask, lu + "_pot"] = reg - self.gdf.loc[mask, lu + "_past"]

    def modify(self, r_number: int, lu_idx: int, direction: int) -> None:
        spec = self.potential_data[r_number - 1][lu_idx]
        if spec.is_log:
            spec.newconst -= math.log10(0.1) * direction
        else:
            spec.newconst += 0.1 * direction
        self._compute_potential(r_number, lu_idx)

    # ── PotentialProtocol ────────────────────────────────────────────────────

    def get_potential(self, lu: str):
        """
        Expõe o potencial já calculado para `lu` sem que o chamador
        (Allocation) precise conhecer a convenção de coluna `<lu>_pot`.
        """
        return self.gdf[lu + "_pot"]

    # ── factory: build from a resolved model spec (TOML) ────────────────────

    @classmethod
    def from_spec(cls, spec: dict, *, demand, land_use_types: list[str], gdf, **_ignored):
        """
        Build a PotentialLinearRegression from a resolved `[model]` spec dict.

        Reads `spec["potential"]` — a list of {lu, const, betas, is_log}
        entries — and `spec["land_use_no_data"]`. Any land use type not
        present in `spec["potential"]` gets a zero-constant, no-driver spec.

        `**_ignored` absorbs kwargs meant for other strategies (e.g.
        `potential_columns`) so a generic executor can call every
        registered strategy's `from_spec` with the same spec dict.
        """
        potential_map = {p.get("lu"): p for p in spec.get("potential", [])}
        potential_data = [[
            RegressionSpec(
                const  = potential_map[lu].get("const", 0.0),
                betas  = potential_map[lu].get("betas", {}),
                is_log = potential_map[lu].get("is_log", False),
            ) if lu in potential_map else RegressionSpec(const=0.0)
            for lu in land_use_types
        ]]
        return cls(
            gdf              = gdf,
            potential_data   = potential_data,
            demand           = demand,
            land_use_types   = land_use_types,
            land_use_no_data = spec.get("land_use_no_data", "outros"),
        )
