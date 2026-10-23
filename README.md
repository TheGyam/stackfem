# stackfem

Steady heat flow through a layered power module stack, from one parameter file
to a converged answer.

- **Geometry.** Gmsh's OpenCASCADE kernel builds the stack (baseplate, solder,
  substrate, die attach, die) as boxes fused at every interface.
- **Mesh.** Gmsh size fields put small elements in the thin solder and die-attach
  layers and grade back to coarse elements around them. Every mesh is quality
  checked before it is solved, and a poor one stops the run.
- **Solve.** CalculiX solves the steady heat flow with quadratic tetrahedra.
- **Study.** The same model is meshed and solved at several refinement levels.
  The results are extrapolated to zero element size, with an error band.
- **Plots.** One post-processing script turns any results folder into the
  convergence plot, a centre-line temperature profile and a map of the die top.

![Mesh convergence](docs/convergence.png)

## Setup

Python 3.11 or newer, and CalculiX's `ccx`.

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # .venv/bin/pip on Linux and macOS
```

CalculiX:

- **Linux:** `sudo apt install calculix-ccx`
- **macOS, Linux or Windows:** from conda-forge,
  `micromamba create -p ~/calculix -c conda-forge calculix`. Activate the
  environment, or on Windows put both `Library\bin` and `Library\mingw-w64\bin` on
  `PATH`.

If `ccx` is not on `PATH`, set `STACKFEM_CCX` to its full path.

## Use

```bash
stackfem geometry params/module.toml   # write the stack as a STEP file
stackfem mesh params/module.toml       # mesh level 0 and print its quality, no solve
stackfem run params/module.toml        # the baseline: mesh, check and solve level 0
stackfem study params/module.toml      # every level, then the convergence report
stackfem post params/module.toml       # redo the report and plots from saved results
```

`mesh` and `run` take `--level n`. Every command takes `--out folder`; by default
results go to `results/<name>/`.

## The parameter file

[params/module.toml](params/module.toml) holds everything: each layer's material,
footprint, thickness and element size, the materials' conductivities, the mesh
grading and refinement ratio, the quality limits, the heat load and the number
of study levels. Copy it to model a different stack. Units are mm, W and °C.

## What comes out

```
results/module/
  params.toml        the parameter file the results came from
  level_0/ ...       one folder per level:
    mesh.msh           the mesh, to open in Gmsh
    module.inp         the CalculiX input deck
    module.frd         CalculiX results, to open in CalculiX GraphiX (cgx)
    result.npz         nodes, elements and temperatures, for the plots
  summary.csv        one row per level: size, max die temperature, R_th, time
  convergence.txt    the same as a table, with the extrapolated answer
  convergence.png    max die temperature against element size
  profile.png        temperature up the centre line
  top.png            temperature over the top of the die
```

## Results for the example module

20 W in a 3 × 3 mm SiC die on sintered silver, AlN substrate, SAC305 solder and
a copper baseplate held at 25 °C.

| level | nodes   | max die temperature (°C) | R_th (K/W) |
| ----- | ------- | ------------------------ | ---------- |
| 0     | 87,361  | 38.891                   | 0.6946     |
| 1     | 150,940 | 38.901                   | 0.6951     |
| 2     | 266,166 | 38.907                   | 0.6953     |
| 3     | 489,404 | 38.910                   | 0.6955     |

The observed order of convergence is 2.69, the extrapolated maximum is
38.915 °C, and the grid convergence index on the finest mesh is 0.016%. The
whole study takes about four minutes on a laptop.

![Temperature along the centre line](docs/profile.png)

## Checks

```bash
pytest
```

The tests check the parameter file, the mesh (every layer fills its box, no
element is inverted, node order matches CalculiX), the quality gate, the
extrapolation, and a full CalculiX run on a three-layer slab against the
temperatures worked out by hand. The solver test is skipped when `ccx` is not
installed.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the code is laid out.
