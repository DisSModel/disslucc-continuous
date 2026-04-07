# src/dissluc/executor/lucc_validation_executor.py
from __future__ import annotations

import io
import time
import struct
import zipfile
import pathlib

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dissmodel.core import Environment
from dissmodel.executor import ExperimentRecord, ModelExecutor
from dissmodel.executor.cli import run_cli
from dissmodel.geo.raster.backend import RasterBackend
from dissmodel.io import load_dataset
from dissmodel.io._utils import write_bytes, write_text
from dissmodel.executor.config import settings

from dissluc import DemandPreComputedValues, load_demand_csv
from dissluc.modules.vector.potential.continuous.linear import PotentialCLinearRegression as VecPotential
from dissluc.modules.vector.allocation.continuous.clue  import AllocationCClueLike        as VecAllocation
from dissluc.modules.raster.potential.continuous.linear import PotentialCLinearRegression as RasPotential
from dissluc.modules.raster.allocation.continuous.clue  import AllocationCClueLike        as RasAllocation
from dissluc.modules.schemas import RegressionSpec, AllocationSpec

# ── Defaults do Lab1 ──────────────────────────────────────────────────────────

LAND_USE_TYPES   = ["f", "d", "outros"]
LAND_USE_NO_DATA = "outros"
STATIC           = {"f": -1, "d": -1, "outros": 1}

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

ALLOCATION_DATA = [[
    AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
    AllocationSpec(static=-1, min_value=0, max_value=1, min_change=0, max_change=1),
    AllocationSpec(static=1,  min_value=0, max_value=1, min_change=0, max_change=1),
]]


class LuccBenchmarkExecutor(ModelExecutor):
    """
    Validation executor for CLUE-like LUCC modeling (Lab1).
    Compares Vector execution, Raster execution, and a TerraME reference dataset.
    
    Expected parameters:
    - n_steps (int): defaults to 7
    - tolerance (float): defaults to 0.01
    - cell_area (float): defaults to 25.0
    - demand_csv (str): Path to demand CSV
    - terrame_reference (str): Path to TerraME ZIP file
    """

    name = "lucc_validation"

    # ── public contract ───────────────────────────────────────────────────────

    def load(self, record: ExperimentRecord) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
        # 1. Carrega o input principal (Shapefile)
        gdf, checksum = load_dataset(record.source.uri, fmt="vector")
        record.source.checksum = checksum

        if record.column_map:
            gdf = gdf.rename(columns={v: k for k, v in record.column_map.items()})

        # 2. Carrega a referência do TerraME via path passado nos parâmetros
        terrame_uri = record.parameters.get("terrame_reference")
        terrame_df  = _load_terrame(pathlib.Path(terrame_uri))
        
        record.add_log(f"Loaded Shapefile: {len(gdf)} cells")
        record.add_log(f"Loaded TerraME Ref: {len(terrame_df)} cells")
        
        return gdf, terrame_df

    def validate(self, record: ExperimentRecord) -> None:
        if not record.source.uri:
            raise ValueError("source.uri is empty — pass the main shapefile.")
        
        if "terrame_reference" not in record.parameters:
            raise ValueError("Missing 'terrame_reference' parameter (path to TerraME ZIP).")
            
        if "demand_csv" not in record.parameters:
            raise ValueError("Missing 'demand_csv' parameter.")

    def run(self, record: ExperimentRecord) -> dict:
        params     = record.parameters
        n_steps    = params.get("n_steps", 7)
        tolerance  = params.get("tolerance", 0.01)
        cell_area  = params.get("cell_area", 25.0)
        demand_csv = params.get("demand_csv")

        gdf_orig, terrame_df = self.load(record)

        # ── vector run ────────────────────────────────────────────────────────
        record.add_log(f"Running Vector Model ({n_steps} steps)...")
        gdf_vec = gdf_orig.copy()
        env_vec = Environment(start_time=1, end_time=n_steps)
        demand  = DemandPreComputedValues(
            annual_demand  = load_demand_csv(demand_csv, LAND_USE_TYPES),
            land_use_types = LAND_USE_TYPES,
        )
        pot_vec = VecPotential(
            gdf=gdf_vec, potential_data=POTENTIAL_DATA, demand=demand,
            land_use_types=LAND_USE_TYPES, land_use_no_data=LAND_USE_NO_DATA,
        )
        VecAllocation(
            gdf=gdf_vec, demand=demand, potential=pot_vec,
            land_use_types=LAND_USE_TYPES, static=STATIC,
            complementar_lu="f", cell_area=cell_area,
            allocation_data=ALLOCATION_DATA,
        )
        
        t0 = time.perf_counter()
        env_vec.run()
        vec_ms = (time.perf_counter() - t0) * 1000 / n_steps
        record.add_log(f"Vector done: {vec_ms:.1f} ms/step")

        # ── raster run ────────────────────────────────────────────────────────
        record.add_log(f"Running Raster Model ({n_steps} steps)...")
        backend, rows, cols = _build_mock_raster(gdf_orig)
        env_ras = Environment(start_time=1, end_time=n_steps)
        demand  = DemandPreComputedValues(
            annual_demand  = load_demand_csv(demand_csv, LAND_USE_TYPES),
            land_use_types = LAND_USE_TYPES,
        )
        pot_ras = RasPotential(
            backend=backend, potential_data=POTENTIAL_DATA, demand=demand,
            land_use_types=LAND_USE_TYPES, land_use_no_data=LAND_USE_NO_DATA,
        )
        RasAllocation(
            backend=backend, demand=demand, potential=pot_ras,
            land_use_types=LAND_USE_TYPES, static=STATIC,
            complementar_lu="f", cell_area=cell_area,
            allocation_data=ALLOCATION_DATA,
        )

        t0 = time.perf_counter()
        env_ras.run()
        ras_ms = (time.perf_counter() - t0) * 1000 / n_steps
        record.add_log(f"Raster done: {ras_ms:.1f} ms/step")

        # ── alignment & metrics ───────────────────────────────────────────────
        record.add_log("Calculating metrics...")
        
        vec_indexed = pd.Series(
            gdf_vec["d"].values,
            index=pd.MultiIndex.from_arrays([rows, cols], names=["row", "col"]),
            name="d_vec"
        )
        ras_indexed = pd.Series(
            backend.get("d")[rows, cols].astype(float),
            index=pd.MultiIndex.from_arrays([rows, cols], names=["row", "col"]),
            name="d_raster"
        )

        df_vt = vec_indexed.to_frame().join(terrame_df["d_out"], how="inner")
        m_vt  = _metrics(df_vt["d_vec"].values, df_vt["d_out"].values, tolerance)

        df_rt = ras_indexed.to_frame().join(terrame_df["d_out"], how="inner")
        m_rt  = _metrics(df_rt["d_raster"].values, df_rt["d_out"].values, tolerance)

        df_vr = vec_indexed.to_frame().join(ras_indexed, how="inner")
        m_vr  = _metrics(df_vr["d_vec"].values, df_vr["d_raster"].values, tolerance)

        all_metrics = {
            "Vector_vs_TerraME": m_vt,
            "Raster_vs_TerraME": m_rt,
            "Vector_vs_Raster":  m_vr,
        }

        # ── scatter plots (in-memory) ─────────────────────────────────────────
        record.add_log("Generating artifacts...")
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        _scatter(axes[0], df_vt["d_vec"], df_vt["d_out"], "Vector d", "TerraME d_out", "Vector vs TerraME", m_vt)
        _scatter(axes[1], df_rt["d_raster"], df_rt["d_out"], "Raster d", "TerraME d_out", "Raster vs TerraME", m_rt)
        _scatter(axes[2], df_vr["d_vec"], df_vr["d_raster"], "Vector d", "Raster d", "Vector vs Raster", m_vr)
        
        plt.suptitle(f"Lab1 — 'd' (deforestation) at step {n_steps}", fontsize=11)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150)
        plt.close()

        return {
            "plot_buf":   buf,
            "report_str": _build_markdown(n_steps, tolerance, vec_ms, ras_ms, all_metrics),
            "metrics":    all_metrics,
        }

    def save(self, result: dict, record: ExperimentRecord) -> ExperimentRecord:
        base_uri = (
            record.output_path
            or f"{settings.default_output_base}/experiments/{record.experiment_id}/lucc_validation"
        )

        record.add_artifact(
            "plot", write_bytes(result["plot_buf"], f"{base_uri}/scatter.png", content_type="image/png")
        )
        record.add_artifact(
            "report", write_text(result["report_str"], f"{base_uri}/report.md", content_type="text/markdown")
        )

        record.output_path = base_uri
        record.metrics     = result["metrics"]
        record.status      = "completed"
        record.add_log(f"Saved artifacts to {base_uri}")
        return record


# ── helpers ───────────────────────────────────────────────────────────────────

def _metrics(a: np.ndarray, b: np.ndarray, tol: float) -> dict:
    diff = np.abs(a - b)
    return {
        "match_pct": float((diff <= tol).mean() * 100),
        "mae":       float(diff.mean()),
        "rmse":      float(np.sqrt((diff**2).mean())),
        "max_err":   float(diff.max()),
        "n_cells":   len(a),
    }

def _scatter(ax, x, y, xlabel, ylabel, title, m):
    ax.scatter(x, y, alpha=0.3, s=4, color="steelblue")
    lim = max(float(np.max(x)), float(np.max(y))) * 1.05
    ax.plot([0, lim], [0, lim], "r--", lw=1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.text(0.05, 0.88,
            f"Match={m['match_pct']:.1f}%\nMAE={m['mae']:.5f}\nRMSE={m['rmse']:.5f}",
            transform=ax.transAxes, fontsize=7,
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

def _build_mock_raster(gdf: gpd.GeoDataFrame) -> tuple[RasterBackend, np.ndarray, np.ndarray]:
    driver_cols = ["assentamen","uc_us","uc_pi","ti","dist_riobr","fertilidad","rodovias"]
    all_cols    = LAND_USE_TYPES + driver_cols

    rows   = gdf["row"].astype(int).values
    cols   = gdf["col"].astype(int).values
    n_rows = int(rows.max()) + 1
    n_cols = int(cols.max()) + 1

    backend = RasterBackend(shape=(n_rows, n_cols), nodata_value=-1)

    mask = np.zeros((n_rows, n_cols), dtype=np.float32)
    mask[rows, cols] = 1.0
    backend.set("mask", mask)

    for col in all_cols:
        arr = np.full((n_rows, n_cols), -1.0, dtype=np.float32)
        if col in gdf.columns:
            arr[rows, cols] = gdf[col].astype(float).values
        else:
            arr[rows, cols] = 0.0
        backend.set(col, arr)

    return backend, rows, cols

def _load_terrame(path: pathlib.Path) -> pd.DataFrame:
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

def _build_markdown(n_steps: int, tol: float, vec_ms: float, ras_ms: float, metrics: dict) -> str:
    lines = [
        "# Lab1 Validation Report\n\n",
        f"**Steps:** {n_steps} | **Tolerance:** {tol}\n\n",
        "## Runtime\n\n",
        f"| Substrate | ms/step | Speedup |\n|---|---|---|\n",
        f"| Vector | {vec_ms:.1f} | 1× |\n",
        f"| Raster | {ras_ms:.1f} | {vec_ms/ras_ms:.1f}× |\n\n",
        "## Accuracy — `d`\n\n",
        "| Comparison | Match % | MAE | RMSE | Max err | N cells |\n",
        "|---|---|---|---|---|---|\n",
    ]
    for label, m in metrics.items():
        lines.append(
            f"| {label.replace('_', ' ')} | {m['match_pct']:.2f}% | {m['mae']:.6f} | "
            f"{m['rmse']:.6f} | {m['max_err']:.6f} | {m['n_cells']} |\n"
        )
    return "".join(lines)


if __name__ == "__main__":
    run_cli(LuccBenchmarkExecutor)