"""
disslucc_continuous.components.potential.vector.precomputed
----------------------------------
Potential taken directly from a suitability surface computed externally
(MaxEnt, Random Forest, an expert map, another DisSModel run, ...)
instead of being fit internally via linear regression.

This is the vector counterpart of LuccME's PotentialCSampleBased in
spirit — a strategy with internals unrelated to PotentialLinearRegression
that is nonetheless a drop-in replacement for it, because AllocationClueLike
only ever talks to PotentialProtocol (get_potential + modify), never to a
concrete class or to the "<lu>_pot" column convention directly.
"""
from __future__ import annotations

from dissmodel.geo import SyncSpatialModel


class PotentialPrecomputed(SyncSpatialModel):
    """
    Continuous potential of change read from one pre-existing suitability
    column per land use, with an optional additive bias used as the
    feedback channel when Allocation's elasticity saturates.

    Unlike PotentialLinearRegression, there is no notion of a regression
    constant, betas, or region-specific equations — the suitability
    surface is assumed static across steps. Allocation does not need to
    know or care about this difference.

    Parameters
    ----------
    suitability_columns : dict[str, str]
        Maps each land use type to the gdf column holding its precomputed
        suitability in [0, 1] (e.g. {"f": "suit_f", "d": "suit_d"}).
    land_use_types : list[str]
        Land use names, same order used across the rest of the model.
    bias_step : float
        Increment applied to the per-lu additive bias each time `modify`
        is called (mirrors the 0.1 nudge PotentialLinearRegression applies
        to its regression constant).
    """

    def setup(
        self,
        suitability_columns: dict[str, str],
        land_use_types:      list[str],
        bias_step:           float = 0.1,
    ) -> None:
        self.suitability_columns = suitability_columns
        self.land_use_types      = land_use_types
        self.bias_step           = bias_step
        self._bias = {lu: 0.0 for lu in land_use_types}
        # _past é criado e gerenciado automaticamente por SyncSpatialModel
        # (via land_use_types) — nada a fazer aqui.

    def execute(self) -> None:
        # Superfície de aptidão é estática por construção; nada a
        # recomputar por passo. Estratégias que dependem de drivers
        # dinâmicos recalculariam aqui, como PotentialLinearRegression faz.
        pass

    # ── PotentialProtocol ────────────────────────────────────────────────────

    def get_potential(self, lu: str):
        col  = self.suitability_columns[lu]
        past = self.gdf[lu + "_past"]
        return self.gdf[col] + self._bias[lu] - past

    def modify(self, r_number: int, lu_idx: int, direction: int) -> None:
        # Regiões não são modeladas por esta estratégia; r_number é
        # ignorado de propósito — o contrato não obriga suporte a regiões.
        lu = self.land_use_types[lu_idx]
        self._bias[lu] += self.bias_step * direction

    # ── factory: build from a resolved model spec (TOML) ────────────────────

    @classmethod
    def from_spec(cls, spec: dict, *, land_use_types: list[str], gdf, **_ignored):
        """
        Build a PotentialPrecomputed from a resolved `[model]` spec dict.

        Expects `spec["potential_columns"]`: a table mapping each land use
        type to the gdf column holding its precomputed suitability, e.g.

            [model.potential_columns]
            f = "suit_f"
            d = "suit_d"
            outros = "suit_outros"

        `demand` is accepted-and-ignored via `**_ignored` — this strategy
        has no notion of adapting to demand history, unlike
        PotentialLinearRegression. A generic executor can call every
        registered strategy's `from_spec` with the same kwargs regardless.
        """
        columns = spec.get("potential_columns", {})
        missing = [lu for lu in land_use_types if lu not in columns]
        if missing:
            raise ValueError(
                f"potential_strategy='precomputed' requires a suitability "
                f"column per land use type in [model.potential_columns]; "
                f"missing: {missing}"
            )
        return cls(
            gdf                  = gdf,
            suitability_columns  = columns,
            land_use_types       = land_use_types,
            bias_step            = spec.get("potential_bias_step", 0.1),
        )

    @classmethod
    def required_columns(cls, spec: dict, land_use_types: list[str]) -> set[str]:
        """Columns this strategy needs beyond land_use_types/driver_columns."""
        return set(spec.get("potential_columns", {}).values())
