"""
disslucc-continuous — DissModel LUC (Land Use Change) library
===========================================================
Port do LuccME para o framework DisSModel (Python / GeoPandas).

Main facade for all components (Science and Infra).
"""

# Re-exporting from components
from .components.demand     import DemandPreComputedValues, load_demand_csv
from .components.potential.raster import PotentialLinearRegression as PotentialRaster
from .components.potential.vector import PotentialLinearRegression as PotentialVector
from .components.allocation.raster import AllocationClueLike as AllocationRaster
from .components.allocation.vector import AllocationClueLike as AllocationVector

# Re-exporting from common
from .common.schemas        import RegressionSpec, AllocationSpec
from .common.protocols      import DemandProtocol, PotentialProtocol

__all__ = [
    "DemandPreComputedValues",
    "PotentialRaster",
    "PotentialVector",
    "AllocationRaster",
    "AllocationVector",
    "RegressionSpec",
    "AllocationSpec",
    "DemandProtocol",
    "PotentialProtocol",
    "load_demand_csv"
]
