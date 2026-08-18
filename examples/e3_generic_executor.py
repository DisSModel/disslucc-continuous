"""
examples/e3_generic_executor.py
=====================================
Level 3 of 3 — the generic executor: models named in TOML.

This is the production `LUCCVectorExecutor` (disslucc_continuous.executors)
used as-is. Nothing here is reimplemented — the point of this level is
that there is nothing left to reimplement. Where example 2 hardcoded
`PotentialLinearRegression` / `AllocationClueLike` / `DemandPreComputedValues`
inside run(), this executor resolves all three by name from
`model.potential_strategy` / `model.allocation_strategy` /
`model.demand_strategy` in the spec (see
`disslucc_continuous.components.registry`) — change the TOML, get a
different model, same executor, same CLI command.

Compare model_explicit_strategies.toml (spelling out the three strategy
names, all at their defaults) against model.toml (leaving them out
entirely — same result, since the executor falls back to
"linear_regression" / "clue_like" / "csv"). Try switching
`potential_strategy` to "precomputed" or `demand_strategy` to "inline"
and see run() build a different Potential/Demand class without a single
code change here.

Run:
    cd examples
    python e3_generic_executor.py run --toml model_explicit_strategies.toml --input data/input/csAC.zip
    python e3_generic_executor.py run --toml model.toml --input data/input/csAC.zip   # same result, strategies omitted
"""
from __future__ import annotations

from dissmodel.executor.cli import run_cli
from disslucc_continuous.executors.clue_like_vector_executor import LUCCVectorExecutor

if __name__ == "__main__":
    run_cli(LUCCVectorExecutor)
