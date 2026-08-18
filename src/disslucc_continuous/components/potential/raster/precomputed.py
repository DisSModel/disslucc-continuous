"""
disslucc_continuous.components.potential.raster.precomputed
----------------------------------
Raster counterpart of potential.vector.precomputed.PotentialPrecomputed.
Reads a precomputed suitability array per land use instead of fitting a
regression internally. See the vector module for the full rationale.
"""
from __future__ import annotations
import numpy as np

from dissmodel.geo import SyncRasterModel


class PotentialPrecomputed(SyncRasterModel):
    """
    Continuous potential of change read from one pre-existing suitability
    array per land use, with an optional additive bias used as the
    feedback channel when Allocation's elasticity saturates.

    Parameters
    ----------
    suitability_arrays : dict[str, str]
        Maps each land use type to the backend array name holding its
        precomputed suitability in [0, 1].
    land_use_types : list[str]
        Land use names, same order used across the rest of the model.
    bias_step : float
        Increment applied to the per-lu additive bias each time `modify`
        is called.
    """

    def setup(
        self,
        backend,
        suitability_arrays: dict[str, str],
        land_use_types:     list[str],
        bias_step:           float = 0.1,
    ) -> None:
        super().setup(backend)
        self.suitability_arrays = suitability_arrays
        self.land_use_types     = land_use_types
        self.bias_step          = bias_step
        self._bias = {lu: 0.0 for lu in land_use_types}

    def execute(self) -> None:
        pass  # superfície de aptidão estática — nada a recomputar por passo

    # ── PotentialProtocol ────────────────────────────────────────────────────

    def get_potential(self, lu: str):
        arr_name = self.suitability_arrays[lu]
        past = self.backend.get(lu + "_past").astype(np.float32)
        suit = self.backend.get(arr_name).astype(np.float32)
        return suit + self._bias[lu] - past

    def modify(self, r_number: int, lu_idx: int, direction: int) -> None:
        lu = self.land_use_types[lu_idx]
        self._bias[lu] += self.bias_step * direction

    # ── factory: build from a resolved model spec (TOML) ────────────────────

    @classmethod
    def from_spec(cls, spec: dict, *, land_use_types: list[str], backend, **_ignored):
        """
        Raster counterpart of PotentialPrecomputed(vector).from_spec.
        Expects `spec["potential_columns"]` mapping lu -> backend array name.
        See the vector module for the full docstring.
        """
        arrays = spec.get("potential_columns", {})
        missing = [lu for lu in land_use_types if lu not in arrays]
        if missing:
            raise ValueError(
                f"potential_strategy='precomputed' requires a suitability "
                f"array per land use type in [model.potential_columns]; "
                f"missing: {missing}"
            )
        return cls(
            backend             = backend,
            suitability_arrays  = arrays,
            land_use_types      = land_use_types,
            bias_step           = spec.get("potential_bias_step", 0.1),
        )

    @classmethod
    def required_columns(cls, spec: dict, land_use_types: list[str]) -> set[str]:
        return set(spec.get("potential_columns", {}).values())
