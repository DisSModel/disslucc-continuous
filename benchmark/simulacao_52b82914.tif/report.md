# Lab1 Validation Report

**Steps:** 6 | **Tolerance:** 0.01

## Runtime

| Substrate | ms/step | Speedup |
|---|---|---|
| Vector | 143.2 | 1× |
| Raster | 39.9 | 3.6× |

## Accuracy — `d`

| Comparison | Match % | MAE | RMSE | Max err | N cells |
|---|---|---|---|---|---|
| Vector vs TerraME | 87.37% | 0.003583 | 0.006188 | 0.027355 | 6574 |
| Raster vs TerraME | 87.37% | 0.003583 | 0.006188 | 0.027355 | 6574 |
| Vector vs Raster | 100.00% | 0.000000 | 0.000000 | 0.000000 | 6574 |
