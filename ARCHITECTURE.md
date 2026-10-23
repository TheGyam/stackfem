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
  solver.py             CalculiX: what every deck shares, running ccx, reading
                        results, and the heat-flow step
  stress.py             The thermal stress step
  study.py              Run one level or all of them; the summary CSV
  post.py               Extrapolation, probing the solution, the plots
  cli.py                The `stackfem` command
tests/                pytest. Small meshes only, so the suite runs in seconds.
docs/                 Images used by the README.
results/              Output. Not tracked by git.
```

## The flow

```
params.toml → geometry → mesh (size fields) → quality check
            → heat-flow deck → ccx → temperatures
            → stress deck (if [mechanics]) → ccx → displacements and stresses
            → result.npz per level → summary.csv → plots and table
```

Each step hands the next one plain data: a dict of parameters, then a dict of
numpy arrays (`nodes`, `elements` per layer, `bottom` nodes, then `temperature`,
`displacement` and `von_mises` per layer). Only `geometry.py` and `mesh.py` talk to
Gmsh, and only `solver.py` and `stress.py` know CalculiX's file formats.

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
- **Solvers.** The heat-flow deck uses CalculiX's iterative Cholesky solver: it
  matches the direct solver to the printed precision and is several times faster.
  The stress step is different. There the iterative solver stops early enough to
  leave stresses of about 0.5% of the thermal stress scale on a stack that should
  carry none, so the stress step uses the direct solver (spooles) unless the
  parameter file asks for `solver = "iterative"`. The direct solver needs much more
  memory on big meshes.
- **Heat flow boundary conditions.** Heat is spread evenly through the source
  layer's volume and leaves through the baseplate bottom, either through a film
  to the coolant (`film`, applied on the element faces found by
  `solver.bottom_faces`) or held at the coolant temperature. All other faces are
  insulated.
- **Stress boundary conditions.** Three bottom nodes stop rigid-body motion and
  nothing else (`stress.supports`). With `support = "flat"` the whole bottom is
  also held at z = 0, as if clamped to a heat sink but free to slide. The stack has
  no stress at `stress_free`; the stress step is one-way, so stress never changes
  the temperatures.
- **Peak stress does not converge.** Where a stiff layer ends on a softer one the
  elastic stress is infinite in theory, so the peak value keeps rising as the
  mesh is refined. The study tracks volume-averaged stress per layer, which does
  converge, and reports the peak only to show where stress gathers.
