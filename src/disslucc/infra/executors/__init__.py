# src/dissluc/infra/executors/__init__.py

from .clue_like_raster_executor import LUCCRasterExecutor
from .clue_like_vector_executor import LUCCVectorExecutor
from .lucc_benchmark_executor import LuccBenchmarkExecutor

__all__ = [
    "LUCCRasterExecutor",
    "LUCCVectorExecutor",
    "LuccBenchmarkExecutor",
    "EXECUTOR_REGISTRY",
]

EXECUTOR_REGISTRY = {
    LUCCRasterExecutor.name:    LUCCRasterExecutor,    # "lucc_raster"
    LUCCVectorExecutor.name:    LUCCVectorExecutor,    # "lucc_vector"
    LuccBenchmarkExecutor.name: LuccBenchmarkExecutor, # "lucc_validation"
}