# Reference LuccME scripts (provenance)

`lab1_main.lua` and `lab1_submodel.lua` are the actual "LuccMe Model
Configurator" output scripts that generated the TerraME reference data
vendored at `benchmark/data/LUCCME_Lab1_2014.zip`. They are kept here
**unmodified** (content is byte-identical to the originals, generated
2017-09-25, "Compatible with LuccME 3.1") so the provenance of the Lab1
validation numbers in this repository can be traced and re-run
independently.

## This is *not* the same script as `terrame/luccme` on GitHub

The public [`terrame/luccme`](https://github.com/terrame/luccme) repository's
own automated test suite, `tests/functional/lab01.lua`, shares this
scenario's calibrated regression coefficients and demand trajectory with
`lab1_submodel.lua` here — enough to look like the same source — but it is
a separate script, with a different convergence parameter, and it did
**not** generate the reference data vendored in `benchmark/data/`:

| | `lab1_submodel.lua` (this folder — actually used) | `tests/functional/lab01.lua` (GitHub look-alike) |
|---|---|---|
| `maxDifference` | **1643** | **5000** |

The README's "Convergence tolerance" note (`maxDifference = 1643`, 7.6%
convergence band) already cites the correct value; this folder makes the
citation concrete and auditable rather than just descriptive text.

Source: local project files provided by the repository maintainer.
