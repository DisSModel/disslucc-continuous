"""
dissluc — DissModel LUC (Land Use Change) library
==================================================
Port do LuccME para o framework DisSModel (Python / GeoPandas).

Importações rápidas:
    from dissluc.demand import DemandPreComputedValues
    from dissluc.vector import PotentialLinearRegression, AllocationClueLike
    from dissluc.schemas import RegressionSpec, AllocationSpec
"""
from .modules.demand.precomputed              import DemandPreComputedValues, load_demand_csv
from .modules.vector.potential.linear         import PotentialLinearRegression
from .modules.vector.allocation.clue          import AllocationClueLike
from .modules.schemas import RegressionSpec, AllocationSpec

__all__ = [
    "DemandPreComputedValues",
    "PotentialLinearRegression",
    "AllocationClueLike",
    "RegressionSpec",
    "AllocationSpec",
    "load_demand_csv"
]
