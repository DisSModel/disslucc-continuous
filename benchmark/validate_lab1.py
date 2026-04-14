"""
validate_lab1.py
================
Validation and benchmark: vector vs raster vs TerraME (Lab1, csAC, 2008-2014).

Usage:
    python validate_lab1.py data/csAC.zip data/cs_ac_2014_terrame.zip

Fix
---
run_raster agora constrói o RasterBackend diretamente dos atributos row/col
do shapefile (grade 89×165), em vez de rasterizar geometricamente com
shapefile_to_raster_backend. Isso garante alinhamento perfeito entre
vetor e raster ao comparar resultados.
"""
from __future__ import annotations

import argparse
import pathlib
import time
import struct
import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dissmodel.core import Environment
from dissmodel.geo.raster.backend import RasterBackend

from dissluc import DemandPreComputedValues, load_demand_csv
from dissluc.vector.potential.linear import PotentialLinearRegression as VecPotential
from dissluc.vector.allocation.clue  import AllocationClueLike        as VecAllocation
from dissluc.raster.potential.linear import PotentialLinearRegression as RasPotential
from dissluc.raster.allocation.clue  import AllocationClueLike        as RasAllocation
from dissluc.schemas import RegressionSpec, AllocationSpec

# ── configuration ─────────────────────────────────────────────────────────────

LAND_USE_TYPES   = ["f", "d", "outros"]
LAND_USE_NO_DATA = "outros"
CELL_AREA        = 25.0
N_STEPS          = 7
#TOLERANCE        = 1e-4
TOLERANCE        = 0.01
DEMAND_CSV       = pathlib.Path("data/examples_demand_lab1.csv")

POTENTIAL_DATA = [[
    RegressionSpec(const=0.7392, betas={
        "assentamen": -0.2193, "uc_us": 0.1754, "uc_pi": 0.09708,
        "ti": 0.1207, "dist_riobr": 0.0000002388, "fertilidad": -0.1313,
    }),
    RegressionSpec(const=0.267, betas={
        "rodovias": -0.0000009922, "assentamen": 0.2294, "uc_us": -0.09867,
        "dist_riobr": -0.0000003216, "fertilidad": 0.1281,
    }),
    RegressionSpec(const=0.0),
]]

STATIC = {"f": -1, "d": -1, "outros": 1}

ALLOCATION_DATA = [[
    AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
    AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
    AllocationSpec(static=1,  min_value=0, max_value=1, min_change=0, max_change=1),
]]

# ── helpers ───────────────────────────────────────────────────────────────────

def metrics(a: np.ndarray, b: np.ndarray, tol: float = TOLERANCE) -> dict:
    diff = np.abs(a - b)
    return {
        "match_pct": float((diff <= tol).mean() * 100),
        "mae":       float(diff.mean()),
        "rmse":      float(np.sqrt((diff**2).mean())),
        "max_err":   float(diff.max()),
        "n_cells":   len(a),
    }


def load_terrame(path: pathlib.Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        dbf = z.read("Lab1_2014.dbf")

    nrecords    = struct.unpack_from("<I", dbf, 4)[0]
    header_size = struct.unpack_from("<H", dbf, 8)[0]
    record_size = struct.unpack_from("<H", dbf, 10)[0]

    fields, foffsets, cur = [], [], 1
    offset = 32
    while dbf[offset] != 0x0D:
        name  = dbf[offset:offset+11].rstrip(b"\x00").decode()
        ftype = chr(dbf[offset+11])
        flen  = dbf[offset+16]
        fields.append((name, ftype, flen))
        foffsets.append(cur)
        cur += flen
        offset += 32

    def val(rec, idx):
        _, _, flen = fields[idx]
        raw = rec[foffsets[idx]: foffsets[idx]+flen].decode("latin1").strip()
        try:    return float(raw)
        except: return raw

    rows = []
    for i in range(nrecords):
        rec = dbf[header_size + i*record_size : header_size + (i+1)*record_size]
        rows.append({fields[j][0]: val(rec, j) for j in range(len(fields))})

    df = pd.DataFrame(rows)
    df["row"] = df["row"].astype(int)
    df["col"] = df["col"].astype(int)
    return df.set_index(["row", "col"])


def build_rc_index(gdf: gpd.GeoDataFrame) -> pd.MultiIndex:
    return pd.MultiIndex.from_arrays(
        [gdf["row"].astype(int).values, gdf["col"].astype(int).values],
        names=["row", "col"],
    )

# ── runners ───────────────────────────────────────────────────────────────────

def run_vector(shp_path: pathlib.Path) -> tuple[gpd.GeoDataFrame, float]:
    gdf    = gpd.read_file(str(shp_path))
    env    = Environment(end_time=N_STEPS - 1)
    demand = DemandPreComputedValues(
        annual_demand  = load_demand_csv(str(DEMAND_CSV), LAND_USE_TYPES),
        land_use_types = LAND_USE_TYPES,
    )
    pot = VecPotential(
        gdf=gdf, potential_data=POTENTIAL_DATA, demand=demand,
        land_use_types=LAND_USE_TYPES, land_use_no_data=LAND_USE_NO_DATA,
    )
    VecAllocation(
        gdf=gdf, demand=demand, potential=pot,
        land_use_types=LAND_USE_TYPES, static=STATIC,
        complementar_lu="f", cell_area=CELL_AREA,
        allocation_data=ALLOCATION_DATA,
    )
    t0 = time.perf_counter()
    env.run()
    ms = (time.perf_counter() - t0) * 1000 / N_STEPS
    return gdf, ms


def run_raster(shp_path: pathlib.Path, gdf_orig: gpd.GeoDataFrame):
    """
    Constrói o RasterBackend diretamente dos atributos row/col do shapefile,
    garantindo que a grade raster (89×165) seja idêntica à grade do shapefile.
    Elimina o erro de alinhamento causado por rasterização geométrica.
    """
    driver_cols = ["assentamen","uc_us","uc_pi","ti","dist_riobr","fertilidad","rodovias"]
    all_cols    = LAND_USE_TYPES + driver_cols

    # coordenadas da grade — derivadas do shapefile
    rows   = gdf_orig["row"].astype(int).values
    cols   = gdf_orig["col"].astype(int).values
    n_rows = int(rows.max()) + 1   # 89
    n_cols = int(cols.max()) + 1   # 165

    b = RasterBackend(shape=(n_rows, n_cols), nodata_value=-1)

    # banda mask: 1.0 = célula válida, 0.0 = fora do extent
    mask_arr = np.zeros((n_rows, n_cols), dtype=np.float32)
    mask_arr[rows, cols] = 1.0
    b.set("mask", mask_arr)

    # popular todos os atributos com nodata=-1 fora do extent
    for col in all_cols:
        arr = np.full((n_rows, n_cols), -1.0, dtype=np.float32)
        if col in gdf_orig.columns:
            arr[rows, cols] = gdf_orig[col].astype(float).values
        else:
            arr[rows, cols] = 0.0
        b.set(col, arr)

    print(f"  grid: {n_rows}×{n_cols}  válidas: {int(mask_arr.sum())}")

    env    = Environment(end_time=N_STEPS - 1)
    demand = DemandPreComputedValues(
        annual_demand  = load_demand_csv(str(DEMAND_CSV), LAND_USE_TYPES),
        land_use_types = LAND_USE_TYPES,
    )
    pot = RasPotential(
        backend=b, potential_data=POTENTIAL_DATA, demand=demand,
        land_use_types=LAND_USE_TYPES, land_use_no_data=LAND_USE_NO_DATA,
    )
    RasAllocation(
        backend=b, demand=demand, potential=pot,
        land_use_types=LAND_USE_TYPES, static=STATIC,
        complementar_lu="f", cell_area=CELL_AREA,
        allocation_data=ALLOCATION_DATA,
    )
    t0 = time.perf_counter()
    env.run()
    ms = (time.perf_counter() - t0) * 1000 / N_STEPS

    # Series indexada por (row,col) do shapefile — alinhamento garantido
    d_series = pd.Series(
        b.get("d")[rows, cols].astype(float),
        index=pd.MultiIndex.from_arrays([rows, cols], names=["row", "col"]),
        name="d_raster",
    )
    return d_series, ms


# ── scatter plot ──────────────────────────────────────────────────────────────

def scatter_plot(ax, x, y, xlabel, ylabel, title, m):
    ax.scatter(x, y, alpha=0.3, s=4, color="steelblue")
    lim = max(float(np.max(x)), float(np.max(y))) * 1.05
    ax.plot([0, lim], [0, lim], "r--", lw=1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.text(0.05, 0.88,
            f"match={m['match_pct']:.1f}%\nMAE={m['mae']:.5f}\nRMSE={m['rmse']:.5f}",
            transform=ax.transAxes, fontsize=7,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))


# ── report ────────────────────────────────────────────────────────────────────

def write_report(results: dict, path: pathlib.Path) -> None:
    vec_ms = results["vec_ms"]
    ras_ms = results["ras_ms"]
    lines = [
        "# Lab1 Validation Report\n\n",
        f"Grid: csAC | Cells: 6,574 | Steps: {N_STEPS} (2008–2014) | Tolerance: {TOLERANCE}\n\n",
        "## Runtime\n\n",
        f"| Substrate | ms/step | Speedup |\n|---|---|---|\n",
        f"| Vector | {vec_ms:.1f} | 1× |\n",
        f"| Raster | {ras_ms:.1f} | {vec_ms/ras_ms:.1f}× |\n\n",
        "## Accuracy — `d` at step 6 (2014)\n\n",
        "| Comparison | Match % | MAE | RMSE | Max err | N cells |\n",
        "|---|---|---|---|---|---|\n",
    ]
    for label, m in results["metrics"].items():
        lines.append(
            f"| {label} | {m['match_pct']:.2f}% | {m['mae']:.6f} | "
            f"{m['rmse']:.6f} | {m['max_err']:.6f} | {m['n_cells']} |\n"
        )
    path.write_text("".join(lines))
    print(f"Report: {path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("shp",     help="csAC.zip")
    p.add_argument("terrame", help="cs_ac_2014_terrame.zip")
    p.add_argument("--tol", type=float, default=TOLERANCE)
    args = p.parse_args()

    shp_path = pathlib.Path(args.shp)
    ter_path = pathlib.Path(args.terrame)

    print("=" * 60)
    print("Lab1 Validation: vector vs raster vs TerraME")
    print("=" * 60)

    print("\n[1/3] TerraME reference...")
    terrame = load_terrame(ter_path)
    print(f"  {len(terrame)} cells  d_out ∈ [{terrame['d_out'].min():.4f}, {terrame['d_out'].max():.4f}]")

    gdf_orig = gpd.read_file(str(shp_path))

    print("\n[2/3] Vector substrate...")
    gdf_result, vec_ms = run_vector(shp_path)
    print(f"  {vec_ms:.1f} ms/step")

    print("\n[3/3] Raster substrate...")
    ras_d_series, ras_ms = run_raster(shp_path, gdf_orig)
    print(f"  {ras_ms:.1f} ms/step")

    # ── align ─────────────────────────────────────────────────────────────────
    print("\nAligning...")

    vec_indexed = pd.Series(
        gdf_result["d"].values,
        index=build_rc_index(gdf_result),
        name="d_vec",
    )

    df_vt = vec_indexed.to_frame().join(terrame["d_out"], how="inner")
    m_vt  = metrics(df_vt["d_vec"].values, df_vt["d_out"].values, args.tol)
    print(f"  vector↔TerraME : {df_vt.shape[0]} cells  match={m_vt['match_pct']:.2f}%  MAE={m_vt['mae']:.6f}")

    df_rt = ras_d_series.to_frame().join(terrame["d_out"], how="inner")
    m_rt  = metrics(df_rt["d_raster"].values, df_rt["d_out"].values, args.tol)
    print(f"  raster↔TerraME : {df_rt.shape[0]} cells  match={m_rt['match_pct']:.2f}%  MAE={m_rt['mae']:.6f}")

    df_vr = vec_indexed.to_frame().join(ras_d_series, how="inner")
    m_vr  = metrics(df_vr["d_vec"].values, df_vr["d_raster"].values, args.tol)
    print(f"  vector↔raster  : {df_vr.shape[0]} cells  match={m_vr['match_pct']:.2f}%  MAE={m_vr['mae']:.6f}")

    # ── plots ──────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    scatter_plot(axes[0], df_vt["d_vec"],    df_vt["d_out"],    "Vector d", "TerraME d_out", "Vector vs TerraME", m_vt)
    scatter_plot(axes[1], df_rt["d_raster"], df_rt["d_out"],    "Raster d", "TerraME d_out", "Raster vs TerraME", m_rt)
    scatter_plot(axes[2], df_vr["d_vec"],    df_vr["d_raster"], "Vector d", "Raster d",      "Vector vs Raster",  m_vr)
    plt.suptitle("Lab1 — d (deforestation) at 2014", fontsize=11)
    plt.tight_layout()
    plt.savefig("validation_scatter.png", dpi=150)
    print("Plot: validation_scatter.png")

    write_report({
        "vec_ms": vec_ms, "ras_ms": ras_ms,
        "metrics": {
            "Vector vs TerraME": m_vt,
            "Raster vs TerraME": m_rt,
            "Vector vs Raster":  m_vr,
        }
    }, pathlib.Path("validation_report.md"))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Runtime   vector={vec_ms:.1f}ms  raster={ras_ms:.1f}ms  speedup={vec_ms/ras_ms:.1f}×")
    print(f"  Vector vs TerraME  match={m_vt['match_pct']:.2f}%  MAE={m_vt['mae']:.6f}")
    print(f"  Raster vs TerraME  match={m_rt['match_pct']:.2f}%  MAE={m_rt['mae']:.6f}")
    print(f"  Vector vs Raster   match={m_vr['match_pct']:.2f}%  MAE={m_vr['mae']:.6f}")


if __name__ == "__main__":
    main()
