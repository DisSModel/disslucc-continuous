# DisSLUCC 🌍

> **Discrete Spatial Library for Land Use Change Modeling** — A Python implementation of LUCC modeling components, built on top of [DissModel](https://github.com/LambdaGeo/dissmodel)

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![LambdaGeo](https://img.shields.io/badge/LambdaGeo-Research-green.svg)](https://github.com/LambdaGeo)

---

## 📖 About

**DisSLUCC** is a Python library that implements spatially explicit components for Land Use and Cover Change (LUCC) modeling. It is directly inspired by the **[LUCCME](http://luccme.ccst.inpe.br)** framework and the **[TerraME](http://www.terrame.org)** environment, originally developed by the Earth System Science Center (CCST/INPE, Brazil).

DisSLUCC runs on top of **[DissModel](https://github.com/LambdaGeo/dissmodel)**, a generic dynamic spatial modeling framework developed by the [LambdaGeo](https://github.com/LambdaGeo) research group. In this ecosystem:

| Original Ecosystem (INPE/CCST) | LambdaGeo Ecosystem | Role |
|-------------------------------|-------------------|------|
| **TerraME** | `dissmodel` | Generic framework for dynamic spatial modeling |
| **LUCCME** | `DisSLUCC` | Domain-specific environment for LUCC modeling |
| **TerraLib** | `geopandas`/`shapely` | Geographic data handling |
| **FillCell** | `dissluc.io` | Cellular space preparation utilities |

```
┌─────────────────────────────────────┐
│  Original Stack (INPE/CCST)         │
│  ┌───────────┐  ┌───────────┐       │
│  │  TerraME  │→ │  LUCCME   │       │
│  │(framework)│  │(LUCC domain)│     │
│  └───────────┘  └───────────┘       │
└─────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────┐
│  LambdaGeo Stack                    │
│  ┌───────────┐  ┌───────────┐       │
│  │ DissModel │→ │  DisSLUCC │       │
│  │(framework)│  │(LUCC domain)│     │
│  └───────────┘  └───────────┘       │
└─────────────────────────────────────┘
```

> ℹ️ **Note**: Both the Python package name and repository name are **DisSLUCC** (`dissluc` for imports).

---

## 🧩 Core Components

DisSLUCC implements the three-pillar LUCC modeling philosophy described by *Verburg et al. (2006)*:

### 1️⃣ Demand Component
Computes the magnitude or quantity of land-use change to be allocated at each time step.

```python
from disslucc import DemandPreComputedValues, load_demand_csv

demand = DemandPreComputedValues(
    annual_demand=load_demand_csv("demand.csv", ["forest", "agriculture"]),
    land_use_types=["forest", "agriculture", "pasture"]
)
```

### 2️⃣ Potential Component
Estimates the suitability or susceptibility of each cell to change, based on spatial driving factors (e.g., distance to roads, protected areas, soil fertility).

```python
from disslucc import PotentialCLinearRegression, RegressionSpec

potential = PotentialCLinearRegression(
    gdf=gdf,
    land_use_types=["forest", "deforested", "other"],
    potential_data=[[
        RegressionSpec(
            const=0.7392,
            betas={
                "assentamen": -0.2193,
                "uc_us": 0.1754,
                "dist_riobr": 2.388e-7,
                "fertilidad": -0.1313,
            }
        ),
        # ... additional specs per land-use type
    ]]
)
```

**Available Potential algorithms:**

| Discrete | Continuous |
|----------|-----------|
| `PotentialDLogisticRegression` | `PotentialCLinearRegression` ✅ |
| `PotentialDNeighSimpleRule` | `PotentialCSpatialLagRegression` |
| `PotentialDSampleBased` | `PotentialCSampleBased` |
| `PotentialDLogisticRegressionNeighAttract` | `PotentialCSpatialLagLinearRegressionMix` |

### 3️⃣ Allocation Component
Spatially distributes changes based on demand and cell-level potential.

```python
from disslucc import AllocationCClueLike, AllocationSpec

AllocationCClueLike(
    gdf=gdf,
    demand=demand,
    potential=potential,
    land_use_types=["forest", "deforested", "other"],
    static={"forest": -1, "deforested": -1, "other": 1},  # -1: demand-directed, 1: static
    complementar_lu="forest",  # land-use type for mass-balance adjustment
    cell_area=25,  # km²
    allocation_data=[[
        AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
        # ... additional specs per land-use type
    ]]
)
```

**Available Allocation algorithms:**

| Discrete | Continuous |
|----------|-----------|
| `AllocationDClueSLike` | `AllocationCClueLike` ✅ |
| `AllocationDSimpleOrdering` | `AllocationCClueLikeSaturation` |
| `AllocationDClueSNeighOrdering` | |

---

## 🚀 Quick Start

### Example: Lab1 (csAC.shp, 2008–2014)

```python
# lab1_main.py
from __future__ import annotations
import argparse, pathlib
import geopandas as gpd
from dissmodel.core import Environment
from dissmodel.visualization import Map

from disslucc import (
    DemandPreComputedValues,
    load_demand_csv,
    PotentialCLinearRegression,
    AllocationCClueLike,
    AllocationSpec,
    RegressionSpec
)

LAND_USE_TYPES   = ["f", "d", "outros"]
LAND_USE_NO_DATA = "outros"
CELL_AREA        = 25    # km²
N_STEPS          = 7     # steps 0…6 (years 2008…2014)

POTENTIAL_DATA = [[
    RegressionSpec(const=0.7392, betas={
        "assentamen": -0.2193, "uc_us": 0.1754, "uc_pi": 0.09708,
        "ti": 0.1207, "dist_riobr": 2.388e-7, "fertilidad": -0.1313,
    }),
    RegressionSpec(const=0.267, betas={
        "rodovias": -9.922e-7, "assentamen": 0.2294, "uc_us": -0.09867,
        "dist_riobr": -3.216e-7, "fertilidad": 0.1281,
    }),
    RegressionSpec(const=0.0),  # "outros" — no betas
]]

STATIC = {"f": -1, "d": -1, "outros": 1}

ALLOCATION_DATA = [[
    AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),  # f
    AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),  # d
    AllocationSpec(static=1,  min_value=0, max_value=1, min_change=0, max_change=1),  # outros
]]

def run(shp_path, save=True):
    shp_path = pathlib.Path(shp_path)
    gdf = gpd.read_file(shp_path)
    print(f"Loaded: {len(gdf)} cells, CRS={gdf.crs}")

    env = Environment(end_time=N_STEPS - 1)

    demand = DemandPreComputedValues(
        annual_demand=load_demand_csv("data/examples_demand_lab1.csv", LAND_USE_TYPES),
        land_use_types=LAND_USE_TYPES,
    )

    potential = PotentialCLinearRegression(
        gdf=gdf,
        potential_data=POTENTIAL_DATA,
        demand=demand,
        land_use_types=LAND_USE_TYPES,
        land_use_no_data=LAND_USE_NO_DATA,
    )

    AllocationCClueLike(
        gdf=gdf,
        demand=demand,
        potential=potential,
        land_use_types=LAND_USE_TYPES,
        static=STATIC,
        complementar_lu="f",
        cell_area=CELL_AREA,
        allocation_data=ALLOCATION_DATA,
    )

    Map(
        gdf=gdf,
        plot_params={
            "column": "f",
            "cmap": "Greens",
            "scheme": "equal_interval",
            "k": 5,
            "legend": True,
        }
    )

    print(f"Simulating {N_STEPS} steps...")
    env.run()
    print("Done.")

    if save:
        out = shp_path.with_name(shp_path.stem + "_result.gpkg")
        gdf.to_file(out, driver="GPKG")
        print(f"Saved: {out}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("shp")
    p.add_argument("--no-save", dest="save", action="store_false")
    args = p.parse_args()
    run(args.shp, args.save)
```

**Run the example:**
```bash
python lab1_main.py csAC.shp                    # Run and save output
python lab1_main.py csAC.shp --chart --no-save  # With chart, without saving
```

---

## 📦 Installation

```bash
# Via pip (coming soon)
pip install disslucc

# From source
git clone https://github.com/LambdaGeo/DisSLUCC.git
cd DisSLUCC
pip install -e .
```

**Dependencies:**
- `dissmodel` (core framework)
- `geopandas`, `shapely`, `pandas`, `numpy`
- `matplotlib`, `seaborn` (visualization)

---

## 🗂️ Project Structure

```
DisSLUCC/
├── disslucc/
│   ├── __init__.py
│   ├── demand/          # Demand components
│   │   ├── precomputed.py
│   │   ├── interpolated.py
│   │   └── external.py
│   ├── potential/       # Potential components
│   │   ├── discrete/    # Categorical land-use algorithms
│   │   └── continuous/  # Percentage-based algorithms
│   ├── allocation/      # Allocation components
│   │   ├── clue_like.py
│   │   └── rules.py
│   ├── io/              # Cellular space utilities (FillCell equivalent)
│   │   ├── cellular_space.py
│   │   └── operators.py  # distance, mode, coverage, etc.
│   └── validation/      # Validation metrics (Costanza, Kappa)
├── labs/                # Reproducible LUCCME Lab examples
│   ├── lab1_discrete/
│   ├── lab1_continuous/
│   └── ...
├── docs/                # Technical documentation
└── tests/               # Unit and integration tests
```

---

## 🎯 Design Philosophy

1. **Modularity**: Demand, Potential, and Allocation components are interchangeable.
2. **Transparency**: Regression coefficients, elasticities, and allocation rules are explicit and version-controlled.
3. **Reproducibility**: Python scripts replace GUI-based workflows for better traceability.
4. **Extensibility**: New components can be implemented by inheriting from base classes.
5. **Integration**: DisSLUCC models can be coupled with other environmental models via `dissmodel.Environment`.

---

## 📚 References & Origins

This project is a conceptual reinterpretation of:

- **LUCCME**: *Land Use and Cover Change Modelling Environment*  
  [http://luccme.ccst.inpe.br](http://luccme.ccst.inpe.br)  
  Carneiro et al. (2013). *Environmental Modelling & Software*, 46, 104–117.

- **TerraME**: Generic programming environment for dynamic spatial modeling  
  [http://www.terrame.org](http://www.terrame.org)

- **LUCC modeling framework**: Verburg et al. (2004, 2006) — Demand–Potential–Allocation structure

- **Validation metric**: Multi-resolution similarity measure (Costanza, 1989)

> ⚠️ **Disclaimer**: DisSLUCC is **not** an official fork or extension of LUCCME/TerraME. It is an independent implementation that preserves the original philosophy and algorithms, adapted to the Python ecosystem and the DissModel architecture.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-component`)
3. Implement your changes and add tests
4. Submit a Pull Request with a clear description of your changes

**Implementing new components**: See `docs/creating_components.md` for implementation guidelines compatible with the LUCCME architecture.

---

## 📄 License

Distributed under the **GPL-3.0 License**. See `LICENSE` for details.

Developed by the **[LambdaGeo](https://github.com/LambdaGeo)** research group.

---

*Built with ❤️ for the open-source environmental modeling community.* 🌱🔬
