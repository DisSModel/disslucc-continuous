"""
dissluc — DissModel LUC (Land Use Change) library
==================================================
Port do LuccME para o framework DisSModel (Python / GeoPandas).

Importações rápidas:
    from dissluc.demand import DemandPreComputedValues
    from dissluc.vector import PotentialCLinearRegression, AllocationCClueLike
    from dissluc.schemas import RegressionSpec, AllocationSpec
"""
from .modules.demand.precomputed              import DemandPreComputedValues, load_demand_csv
from .modules.vector.potential.continuous.linear import PotentialCLinearRegression
from .modules.vector.allocation.continuous.clue  import AllocationCClueLike
from .modules.schemas import RegressionSpec, AllocationSpec

__all__ = [
    "DemandPreComputedValues",
    "PotentialCLinearRegression",
    "AllocationCClueLike",
    "RegressionSpec",
    "AllocationSpec",
    "load_demand_csv"
]
