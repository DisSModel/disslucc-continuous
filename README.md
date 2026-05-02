# DisSLUCC-Continuous 🌍

> **Continuous Spatial Library for Land Use Change Modeling** — A Python implementation of continuous LUCC modeling components (LUCCME-like), built on top of [DissModel](https://github.com/LambdaGeo/dissmodel)

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![LambdaGeo](https://img.shields.io/badge/LambdaGeo-Research-green.svg)](https://github.com/LambdaGeo)

---

## 📖 About

**DisSLUCC-Continuous** is a Python library that implements spatially explicit components for continuous Land Use and Cover Change (LUCC) modeling. It is directly inspired by the **[LUCCME](http://luccme.ccst.inpe.br)** framework and the **[TerraME](http://www.terrame.org)** environment, originally developed by the Earth System Science Center (CCST/INPE, Brazil).

DisSLUCC-Continuous focus on **continuous** land use change (area/percentage per cell), equivalent to the LUCCME core components.

| Original Ecosystem (INPE/CCST) | LambdaGeo Ecosystem | Role |
|-------------------------------|-------------------|------|
| **TerraME** | `dissmodel` | Generic framework for dynamic spatial modeling |
| **LUCCME** | `DisSLUCC-Continuous` | Domain-specific environment for continuous LUCC modeling |
| **TerraLib** | `geopandas`/`shapely` | Geographic data handling |
| **FillCell** | `dissluc.io` | Cellular space preparation utilities |

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  Original Stack (INPE/CCST)         │     │  LambdaGeo Stack                    │
│  ┌───────────┐  ┌───────────┐       │     │  ┌───────────┐  ┌───────────┐       │
│  │  TerraME  │→ │  LUCCME   │       │  →  │  │ DissModel │→ │  DisSLUCC │       │
│  │(framework)│  │(LUCC dom.)│       │     │  │(framework)│  │(continuous)       │
│  └───────────┘  └───────────┘       │     │  └───────────┘  └───────────┘       │
└─────────────────────────────────────┘     └─────────────────────────────────────┘

> ℹ️ **Note**: Both the Python package name and repository name are **DisSLUCC-Continuous** (`dissluc` for imports).

---

## 🚀 Quick Start

DisSLUCC supports two usage modes that share the same model code — **CLI local** for development and exploration, **Platform API** for reproducible production runs.

### CLI local (development)

```bash
# Vector substrate
python lab1_vector.py run \
  --input data/input/csAC.zip \
  --param interactive=True

# Raster substrate
python lab1_raster.py run \
  --input  data/input/csAC.zip \
  --output data/output/result.tif \
  --param  interactive=True \
  --param  n_steps=7

# Load parameters from TOML (calibrated coefficients)
python lab1_raster.py run \
  --input data/input/csAC.zip \
  --toml  examples/model.toml

# Validate executor data contract without running
python lab1_raster.py validate --input data/input/csAC.zip

# Run the Benchmark suite (Vector vs Raster vs TerraME/LUCCME comparison)
python -m disslucc.infra.executors.lucc_benchmark_executor run \
  --input  examples/data/input/csAC.zip \
  --output ./benchmark/ \
  --param  demand_csv=examples/data/input/examples_demand_lab1.csv \
  --param  terrame_reference=benchmark/data/LUCCME_Lab1_2014.zip \
  --param  n_steps=6 \
  --param  tolerance=0.01

# Show resolved parameters
python lab1_raster.py show --toml examples/model.toml
```

### Platform API (production / reproducibility)

```bash
# Submit job
curl -X POST http://localhost:8000/submit_job \
  -H "X-API-Key: chave-sergio" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name":    "lucc_raster",
    "input_dataset": "s3://dissmodel-inputs/csAC.zip",
    "parameters":    {"n_steps": 7}
  }'

# Check status
curl -H "X-API-Key: chave-sergio" \
  http://localhost:8000/job/<experiment_id>

# Reproduce exact experiment
curl -X POST http://localhost:8000/experiments/<id>/reproduce \
  -H "X-API-Key: chave-sergio"
```

---

## 🧩 Core Components

DisSLUCC implements the three-pillar LUCC modeling philosophy described by *Verburg et al. (2006)*:

### 1️⃣ Demand Component

Computes the magnitude of land-use change to allocate at each time step.

```python
from dissluc import DemandPreComputedValues, load_demand_csv

demand = DemandPreComputedValues(
    annual_demand  = load_demand_csv("demand.csv", ["f", "d", "outros"]),
    land_use_types = ["f", "d", "outros"],
)
```

### 2️⃣ Potential Component

Estimates the suitability of each cell to change, based on spatial driving factors.

```python
from dissluc import PotentialLinearRegression, RegressionSpec

potential = PotentialLinearRegression(
    gdf              = gdf,
    land_use_types   = ["f", "d", "outros"],
    land_use_no_data = "outros",
    potential_data   = [[
        RegressionSpec(const=0.7392, betas={
            "assentamen": -0.2193, "uc_us": 0.1754,
            "dist_riobr": 2.388e-7, "fertilidad": -0.1313,
        }),
        RegressionSpec(const=0.267, betas={
            "rodovias": -9.922e-7, "assentamen": 0.2294,
        }),
        RegressionSpec(const=0.0),  # "outros" — no betas
    ]],
)
```

**Available algorithms:**

| Discrete | Continuous |
|----------|-----------|
| `PotentialDLogisticRegression` | `PotentialLinearRegression` ✅ |
| `PotentialDNeighSimpleRule` | `PotentialCSpatialLagRegression` |
| `PotentialDSampleBased` | `PotentialCSampleBased` |

### 3️⃣ Allocation Component

Spatially distributes changes based on demand and cell-level potential.

```python
from dissluc import AllocationClueLike, AllocationSpec

AllocationClueLike(
    gdf             = gdf,
    demand          = demand,
    potential       = potential,
    land_use_types  = ["f", "d", "outros"],
    static          = {"f": -1, "d": -1, "outros": 1},
    complementar_lu = "f",
    cell_area       = 25.0,  # km²
    allocation_data = [[
        AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
        AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
        AllocationSpec(static=1,  min_value=0, max_value=1, min_change=0, max_change=1),
    ]],
)
```

**Available algorithms:**

| Discrete | Continuous |
|----------|-----------|
| `AllocationDClueSLike` | `AllocationClueLike` ✅ |
| `AllocationDSimpleOrdering` | `AllocationClueLikeSaturation` |

---

## 🗂️ Executor Architecture

DisSLUCC follows the DissModel `ModelExecutor` pattern — each executor separates science from infrastructure. The same model runs locally via CLI or on the platform via API without changing a single line.

```
Science Layer (Model / Salabim)
  PotentialLinearRegression, AllocationClueLike, DemandPreComputedValues
  → only knows math, geometry and time

Infrastructure Layer (ModelExecutor)
  LUCCRasterExecutor, LUCCVectorExecutor, LUCCBenchmarkExecutor
  → only knows URIs, MinIO, column_map, parameters
```

### Executors available

| name | Substrate | Input → Output | Description |
|------|-----------|----------------|-------------|
| `lucc_raster` | RasterBackend / NumPy | Shapefile → GeoTIFF | Production raster simulation |
| `lucc_vector` | GeoDataFrame | Shapefile → GeoPackage | Production vector simulation |
| `lucc_benchmark` | Both | Shapefile → MD + PNG | Vector vs Raster vs TerraME comparison |

### Benchmark executor

The `LUCCBenchmarkExecutor` is a meta-executor that runs vector and raster substrates in a single pass and compares both against a TerraME/LUCCME reference result. It generates a Markdown report and scatter plots — the primary tool for validating numerical equivalence before publishing results.

```bash
python -m dissluc.infra.executors.lucc_benchmark_executor run \
  --input  examples/data/input/csAC.zip \
  --output ./benchmark/ \
  --param  demand_csv=examples/data/input/examples_demand_lab1.csv \
  --param  terrame_reference=benchmark/data/LUCCME_Lab1_2014.zip \
  --param  n_steps=6 \
  --param  tolerance=0.01
```

Output:
```
benchmark/
  report.md    ← runtime comparison + accuracy metrics (match %, MAE, RMSE) per substrate and band
  scatter.png  ← scatter plots: Vector vs Raster vs TerraME for each land-use band
```

### Implementing a custom executor

```python
# my_lucc_executor.py
from dissmodel.executor     import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.io           import load_dataset, save_dataset


class MyLUCCExecutor(ModelExecutor):
    name = "my_lucc"

    def load(self, record: ExperimentRecord):
        gdf, checksum = load_dataset(record.source.uri)
        record.source.checksum = checksum
        if record.column_map:
            gdf = gdf.rename(columns={v: k for k, v in record.column_map.items()})
        return gdf

    def run(self, record: ExperimentRecord):
        from dissmodel.core import Environment
        from dissluc import DemandPreComputedValues, load_demand_csv
        from dissluc.vector.potential.linear import PotentialLinearRegression
        from dissluc.vector.allocation.clue  import AllocationClueLike

        params = record.parameters
        gdf    = self.load(record)
        env    = Environment(end_time=params.get("n_steps", 7) - 1)

        demand    = DemandPreComputedValues(...)
        potential = PotentialLinearRegression(gdf=gdf, ...)
        AllocationClueLike(gdf=gdf, ...)

        env.run()
        return gdf

    def save(self, result, record: ExperimentRecord) -> ExperimentRecord:
        uri      = record.output_path or "output.gpkg"
        checksum = save_dataset(result, uri)
        record.output_path   = uri
        record.output_sha256 = checksum
        record.status        = "completed"
        return record


if __name__ == "__main__":
    run_cli(MyLUCCExecutor)
```

### model.toml — calibrated coefficients

Parameters and regression coefficients are stored in a TOML file, separate from code. In the platform, this lives in `dissmodel-configs` and is version-controlled by the LambdaGeo group.

```toml
# examples/model.toml

[model.parameters]
resolution = 5000.0
n_steps    = 7
demand_csv = "data/examples_demand_lab1.csv"

land_use_types   = ["f", "d", "outros"]
land_use_no_data = "outros"
complementar_lu  = "f"
cell_area        = 25.0

[model.driver_columns]
cols = ["assentamen", "uc_us", "uc_pi", "ti", "dist_riobr", "fertilidad", "rodovias"]

[model.static]
f      = -1
d      = -1
outros = 1

[[model.potential]]
lu    = "f"
const = 0.7392
  [model.potential.betas]
  assentamen = -0.2193
  uc_us      =  0.1754
  uc_pi      =  0.09708
  ti         =  0.1207
  dist_riobr =  0.0000002388
  fertilidad = -0.1313

[[model.potential]]
lu    = "d"
const = 0.267
  [model.potential.betas]
  rodovias   = -0.0000009922
  assentamen =  0.2294
  uc_us      = -0.09867
  dist_riobr = -0.0000003216
  fertilidad =  0.1281

[[model.potential]]
lu    = "outros"
const = 0.0

[[model.allocation]]
lu         = "f"
static     = -1
min_value  = 0
max_value  = 1
min_change = 0
max_change = 1

[[model.allocation]]
lu         = "d"
static     = -1
min_value  = 0
max_value  = 1
min_change = 0
max_change = 1

[[model.allocation]]
lu         = "outros"
static     = 1
min_value  = 0
max_value  = 1
min_change = 0
max_change = 1
```

---

## 📦 Installation

```bash
# Via pip
pip install disslucc-continuous

# From source
git clone https://github.com/LambdaGeo/DisSLUCC.git
cd DisSLUCC
pip install -e .
```

**Dependencies:** `dissmodel`, `geopandas`, `shapely`, `pandas`, `numpy`, `rasterio`, `matplotlib`

---

## 🗂️ Project Structure

```
DisSLUCC-Continuous/
├── src/dissluc/
│   ├── __init__.py          # Main facade (exports models and schemas)
│   ├── components/          # Science Layer (Models)
│   │   ├── demand/
│   │   ├── potential/
│   │   │   ├── raster/
│   │   │   └── vector/
│   │   └── allocation/
│   │       ├── raster/
│   │       └── vector/
│   ├── infra/               # Infrastructure Layer (Executors)
│   │   └── executors/
│   │       ├── clue_like_raster_executor.py
│   │       ├── clue_like_vector_executor.py
│   │       └── lucc_benchmark_executor.py
│   └── common/              # Common Layer (Schemas and Protocols)
│       ├── schemas.py       # RegressionSpec, AllocationSpec
│       └── protocols.py     # Component interfaces
├── examples/
│   ├── lab1_raster.py
│   ├── lab1_vector.py
│   └── ...
├── benchmark/
└── ...
```

---

## 🎯 Design Philosophy

1. **Modularity** — Demand, Potential, and Allocation are interchangeable components.
2. **Transparency** — Regression coefficients and allocation rules are explicit in TOML, version-controlled.
3. **Reproducibility** — Each experiment records model commit, input checksum, and resolved spec via `ExperimentRecord`.
4. **Two substrates** — Same algorithms available for vector (GeoDataFrame) and raster (RasterBackend/NumPy).
5. **Executor pattern** — Science layer never knows about files or cloud; infrastructure layer never calculates spatial equations.
6. **Benchmark-first validation** — `lucc_benchmark` validates numerical equivalence between substrates and against TerraME/LUCCME reference results before any production use.

---

## 📚 References

- **LUCCME**: Carneiro et al. (2013). *Environmental Modelling & Software*, 46, 104–117. [http://luccme.ccst.inpe.br](http://luccme.ccst.inpe.br)
- **TerraME**: [http://www.terrame.org](http://www.terrame.org)
- **Demand–Potential–Allocation framework**: Verburg et al. (2004, 2006)
- **Validation metric**: Multi-resolution similarity (Costanza, 1989)

> ⚠️ **Disclaimer**: DisSLUCC is **not** an official fork or extension of LUCCME/TerraME. It is an independent Python implementation that preserves the original philosophy and algorithms, adapted to the DissModel architecture.

---

## 🤝 Contributing

1. Fork the repository and create a feature branch
2. Implement changes and add tests
3. Submit a Pull Request with a clear description

To register a new model in the platform, open a PR in [dissmodel-configs](https://github.com/LambdaGeo/dissmodel-configs) with a TOML spec pointing to your package.

---

## 📄 License

Distributed under the **GPL-3.0 License**. Developed by the **[LambdaGeo](https://github.com/LambdaGeo)** research group.

---

*Built with ❤️ for the open-source environmental modeling community.* 🌱🔬

