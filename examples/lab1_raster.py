

from dissmodel.executor.cli import run_cli
from disslucc.infra.executors.clue_like_raster_executor import LUCCRasterExecutor


if __name__ == "__main__":
    run_cli(LUCCRasterExecutor)