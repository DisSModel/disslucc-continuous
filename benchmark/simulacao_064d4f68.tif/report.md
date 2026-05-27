# Lab1 Validation Report

**Steps:** 6 | **Tolerance:** 0.01

## Runtime

| Substrate | ms/step | Speedup |
|---|---|---|
| Vector | 122.5 | 1× |
| Raster | 31.6 | 3.9× |

## Accuracy — `d`

| Comparison | Match % | MAE | RMSE | Max err | N cells |
|---|---|---|---|---|---|
| Vector vs TerraME | 97.09% | 0.002276 | 0.003882 | 0.015603 | 6574 |
| Raster vs TerraME | 97.09% | 0.002276 | 0.003882 | 0.015604 | 6574 |
| Vector vs Raster | 100.00% | 0.000000 | 0.000000 | 0.000000 | 6574 |
