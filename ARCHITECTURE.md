# Architecture

How the code is organised, and the rules that keep it that way.

## Where things live

```
params/               Parameter files. One file describes one complete run.
src/stackfem/
  params.py             Read and check a parameter file
  geometry.py           Build the stack in Gmsh (OpenCASCADE)
  mesh.py               Size fields, meshing, and the mesh as numpy arrays
  quality.py            Element quality checks and the quality table
  solver.py             CalculiX: write the deck, run ccx, read temperatures
  study.py              Run one level or all of them; the summary CSV
  post.py               Extrapolation, probing the solution, the plots
  cli.py                The `stackfem` command
tests/                pytest. Small meshes only, so the suite runs in seconds.
docs/                 Images used by the README.
results/              Output. Not tracked by git.
```

## The flow

```
params.toml → geometry → mesh (size fields) → quality check → CalculiX deck → ccx
           → temperatures → result.npz per level → summary.csv → plots and table
```

Each step hands the next one plain data: a dict of parameters, then a dict of
numpy arrays (`nodes`, `elements` per layer, `cold` nodes, and later
`temperature`). Only `geometry.py` and `mesh.py` talk to Gmsh, and only
`solver.py` knows CalculiX's file formats.

## The rules

1. **The parameter file is the only input.** Nothing about the model is
   hard-coded in Python. A new stack is a new `.toml` file, not a code change.
2. **Every mesh goes through the quality check.** `mesh.generate` runs it before
   returning, so no caller can skip it. A failing mesh raises `QualityError`.
3. **Post-processing reads files, not memory.** `post.py` works from a results
   folder alone, so plots can be redone without solving again.
4. **Units are mm, W and °C everywhere.** Conductivity is entered in W/(m K);
   `solver.py` is the one place that converts to the deck's mm and mW.

## Things worth knowing

- **Node order.** Gmsh and CalculiX number the ten nodes of a quadratic
  tetrahedron differently: the last two mid-edge nodes swap. Arrays keep Gmsh's
  order; `solver.GMSH_TO_CCX` reorders when writing the deck, and a test checks it.
- **Size fields.** Each layer has a Box field: its own size inside, growing
  linearly over `grading` mm to the coarsest size outside. The background field is
  the minimum of all of them, which is what puts the small elements in the thin
  layers.
- **Refinement.** Level n divides every size by `refinement_ratio ** n`. The thin
  layers limit how far the mesh can coarsen, so the element count does not grow by
  exactly the cube of the ratio. The extrapolation therefore uses the measured
  size, (volume / nodes)^(1/3), and the Celik et al. (2008) method, which allows
  unequal ratios between levels.
- **Solver.** The deck asks for CalculiX's iterative Cholesky solver. It matches
  the default direct solver to the printed precision and is several times faster.
- **Boundary conditions.** The baseplate bottom is held at a fixed temperature
  (an ideal cold plate). All other faces are insulated. The heat is spread evenly
  through the source layer's volume.
