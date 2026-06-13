from .clue_like_raster_executor import LUCCRasterExecutor
from .clue_like_vector_executor import LUCCVectorExecutor
from .lucc_benchmark_executor import LUCCBenchmarkExecutor, LuccBenchmarkExecutor

__all__ = [
    "LUCCRasterExecutor",
    "LUCCVectorExecutor",
    "LUCCBenchmarkExecutor",
    "LuccBenchmarkExecutor",
    "EXECUTOR_REGISTRY",
]

EXECUTOR_REGISTRY = {
    LUCCRasterExecutor.name:    LUCCRasterExecutor,    # "lucc_raster"
    LUCCVectorExecutor.name:    LUCCVectorExecutor,    # "lucc_vector"
    LUCCBenchmarkExecutor.name: LUCCBenchmarkExecutor, # "lucc_benchmark"
}