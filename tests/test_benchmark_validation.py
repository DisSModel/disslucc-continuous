"""
Benchmark validation: compares Vector and Raster substrates against the
TerraME/LUCCME Lab1 reference result.

Asserts MAE and RMSE < tolerance=0.01 for Vector_vs_TerraME and
Raster_vs_TerraME, confirming numerical equivalence with the original model.
"""
import pathlib
import pytest

from disslucc_continuous.executors import LUCCBenchmarkExecutor
from dissmodel.executor import ExperimentRecord

ROOT = pathlib.Path(__file__).parent.parent

INPUT_ZIP    = ROOT / "examples" / "data" / "input" / "csAC.zip"
DEMAND_CSV   = ROOT / "examples" / "data" / "input" / "examples_demand_lab1.csv"
TERRAME_ZIP  = ROOT / "benchmark" / "data" / "LUCCME_Lab1_2014.zip"

TOLERANCE = 0.01
N_STEPS   = 6


@pytest.fixture(scope="module")
def benchmark_metrics():
    """Run the benchmark executor once and return the metrics dict."""
    executor = LUCCBenchmarkExecutor()

    record = ExperimentRecord(
        model_name  = "lucc_benchmark",
        source      = {"uri": str(INPUT_ZIP)},
        parameters  = {
            "demand_csv":        str(DEMAND_CSV),
            "terrame_reference": str(TERRAME_ZIP),
            "n_steps":           N_STEPS,
            "tolerance":         TOLERANCE,
        },
    )

    data    = executor.load(record)
    result  = executor.run(data, record)
    return result["metrics"]


@pytest.mark.skipif(not INPUT_ZIP.exists(), reason="example data not found")
@pytest.mark.skipif(not TERRAME_ZIP.exists(), reason="benchmark reference not found")
class TestBenchmarkValidation:
    def test_vector_vs_terrame_mae(self, benchmark_metrics):
        mae = benchmark_metrics["Vector_vs_TerraME"]["mae"]
        assert mae < TOLERANCE, f"Vector_vs_TerraME MAE={mae:.6f} exceeds tolerance={TOLERANCE}"

    def test_vector_vs_terrame_rmse(self, benchmark_metrics):
        rmse = benchmark_metrics["Vector_vs_TerraME"]["rmse"]
        assert rmse < TOLERANCE, f"Vector_vs_TerraME RMSE={rmse:.6f} exceeds tolerance={TOLERANCE}"

    def test_raster_vs_terrame_mae(self, benchmark_metrics):
        mae = benchmark_metrics["Raster_vs_TerraME"]["mae"]
        assert mae < TOLERANCE, f"Raster_vs_TerraME MAE={mae:.6f} exceeds tolerance={TOLERANCE}"

    def test_raster_vs_terrame_rmse(self, benchmark_metrics):
        rmse = benchmark_metrics["Raster_vs_TerraME"]["rmse"]
        assert rmse < TOLERANCE, f"Raster_vs_TerraME RMSE={rmse:.6f} exceeds tolerance={TOLERANCE}"
