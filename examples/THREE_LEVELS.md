# Three levels of "how much framework do I need?"

Three runnable variants of the same Lab1 model (real data:
`data/input/csAC.zip` + `data/input/examples_demand_lab1.csv`), showing
the progression from a bare TerraME/LuccME-style script to the full
generic executor. Same 7-step run, same output shape, at each level —
only how much is wired up for you changes.

| | file | executor pattern? | which model classes? | runnable via CLI? |
|---|---|---|---|---|
| 1 | `e1_bare_environment.py` | no | hardcoded imports, hardcoded params | no — `python e1_bare_environment.py` |
| 2 | `e2_executor_fixed_models.py` | yes (`ModelExecutor` + `run_cli`) | hardcoded imports inside `run()`, params from TOML | yes |
| 3 | `e3_generic_executor.py` | yes — the real `LUCCVectorExecutor` | resolved by name from `model.*_strategy` in TOML | yes |

## 1 — bare Environment

The closest thing to a `.lua` script: direct imports, hardcoded
constants, models instantiated straight into an `Environment`, `env.run()`.
No lifecycle, no CLI, no spec file.

```bash
python e1_bare_environment.py
```

## 2 — executor, fixed models

Adds the `ModelExecutor` lifecycle (`load`/`run`/`save`) and the CLI on
top of level 1. Regression coefficients and land use types now come
from a TOML spec, but *which Python classes* build the model
(`PotentialLinearRegression`, `AllocationClueLike`,
`DemandPreComputedValues`) is still fixed in `run()` — this is what
`LUCCVectorExecutor` looked like before it grew a strategy registry.

```bash
python e2_executor_fixed_models.py run --toml model.toml --input data/input/csAC.zip
```

## 3 — generic executor

The production executor (`disslucc_continuous.executors.LUCCVectorExecutor`)
used as-is — nothing reimplemented here, that's the point. Potential/
Allocation/Demand are resolved by name from `model.potential_strategy` /
`model.allocation_strategy` / `model.demand_strategy` in the spec (see
`disslucc_continuous.components.registry`). `model_explicit_strategies.toml`
spells the three names out at their defaults; `model.toml` omits them
entirely — same result either way.

```bash
python e3_generic_executor.py run --toml model_explicit_strategies.toml --input data/input/csAC.zip
python e3_generic_executor.py run --toml model.toml --input data/input/csAC.zip   # same result
```

Try changing `potential_strategy` to `"precomputed"` or `demand_strategy`
to `"inline"` in the TOML and re-running — no code changes needed at
this level, only at level 2.

**Nota (16/08/2026):** até esta versão, `[model.parameters]` (onde
`land_use_types`, `complementar_lu`, `potential_strategy` etc. vivem)
não chegava a `spec` dentro de `run()` quando carregado pela CLI real do
`dissmodel` — caía silenciosamente nos defaults do código. Corrigido nos
dois executores de produção (merge de `record.parameters` em `spec`
antes de qualquer `spec.get(...)`); veja o changelog do patch 6.
