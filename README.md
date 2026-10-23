# stackfem

[![tests](https://github.com/TheGyam/stackfem/actions/workflows/tests.yml/badge.svg)](https://github.com/TheGyam/stackfem/actions/workflows/tests.yml)

Heat flow and thermal stress in a layered power module stack, from one parameter
file to a converged answer.

- **Geometry.** Gmsh's OpenCASCADE kernel builds the stack (baseplate, solder,
  substrate, die attach, die) as boxes fused at every interface.
- **Mesh.** Gmsh size fields put small elements in the thin solder and die-attach
  layers and grade back to coarse elements around them. Every mesh is quality
  checked before it is solved, and a poor one stops the run.
- **Heat flow.** CalculiX solves the steady heat flow with quadratic tetrahedra.
  Heat leaves through the bottom of the baseplate, either into a coolant through a
  heat transfer coefficient or into an ideal cold plate.
- **Thermal stress.** The temperatures are then applied to an elastic model of the
  same mesh, which gives the displacements and the stress in every layer.
- **Study.** The same model is meshed and solved at several refinement levels.
  Each result is extrapolated to zero element size, with an error band.
- **Plots.** One post-processing script turns any results folder into the
  convergence plots, a centre-line temperature profile, a map of the die top and
  the stress in each layer.
- **Window.** A desktop window holds every parameter in a form, runs the study and
  shows the plots. Everything it does can also be done from the command line.

![Mesh convergence](docs/convergence.png)

## Contents

- [Setup](#setup)
- [Quick start](#quick-start)
- [The window](#the-window)
- [The command line](#the-command-line)
- [The parameter file](#the-parameter-file)
- [What comes out](#what-comes-out)
- [Results for the example module](#results-for-the-example-module)
- [What the model leaves out](#what-the-model-leaves-out)
- [Troubleshooting](#troubleshooting)
- [Checks](#checks)

## Setup

You need Python 3.11 or newer, Git, and CalculiX's solver, `ccx`.

### 1. Get the code and install it

```bash
git clone https://github.com/TheGyam/stackfem
```
```bash
cd stackfem
```
```bash
python -m venv .venv
```

Then install stackfem into that environment. `gui` adds the window (PySide6) and
`dev` adds the tests (pytest); leave out what you don't need.

- **Windows:** `.venv\Scripts\pip install -e ".[gui,dev]"`
- **Linux and macOS:** `.venv/bin/pip install -e ".[gui,dev]"`

This also installs Gmsh, NumPy and Matplotlib. The commands below assume the
environment is active (`.venv\Scripts\activate` on Windows,
`source .venv/bin/activate` elsewhere); otherwise put `.venv\Scripts\` or
`.venv/bin/` in front of `stackfem` and `stackfem-gui`.

### 2. Install CalculiX

**Linux (Debian, Ubuntu):**

```bash
sudo apt install calculix-ccx
```

Gmsh also needs a few system libraries that a minimal Linux may not have:

```bash
sudo apt install libglu1-mesa libxcursor1 libxft2 libxinerama1
```

**Windows**, from conda-forge with micromamba, a small package manager. In
PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\micromamba" | Out-Null; Invoke-WebRequest https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64 -OutFile "$env:USERPROFILE\micromamba\micromamba.exe"
```
```powershell
& "$env:USERPROFILE\micromamba\micromamba.exe" create -y -p "$env:USERPROFILE\micromamba\calculix" -c conda-forge calculix
```

**macOS:** the same from conda-forge, with micromamba from Homebrew
(`brew install micromamba`), then
`micromamba create -p ~/calculix -c conda-forge calculix`, and set
`STACKFEM_CCX` to `~/calculix/bin/ccx`.

### 3. Tell stackfem where CalculiX is (Windows)

On Linux, `ccx` is already on `PATH`. On Windows, CalculiX needs both of its DLL
folders on `PATH`, and `STACKFEM_CCX` names the program. Run this in each new
PowerShell window before using stackfem, or add the same values to your user
environment variables to make them permanent:

```powershell
$C = "$env:USERPROFILE\micromamba\calculix\Library"; $env:PATH = "$C\bin;$C\mingw-w64\bin;$env:PATH"; $env:STACKFEM_CCX = "$C\bin\ccx.exe"
```

On any system, `STACKFEM_CCX` can point at a `ccx` that is not on `PATH`.

## Quick start

```bash
stackfem-gui
```

The window opens with the example module filled in. Set **Levels** to 1 and click
**Run**. After two or three minutes the tabs show the plots for the baseline mesh.
Set **Levels** back to 4 for the full convergence study, which takes about 20
minutes.

Or, from the command line:

```bash
stackfem run params/module.toml
```

## The window

```bash
stackfem-gui                    # opens params/module.toml
stackfem-gui my_stack.toml      # opens another parameter file
```

![The StackFEM window](docs/gui.png)

1. **Edit the parameters** on the left.
   - **Layers**, bottom to top: name, material, width, depth, thickness and mesh
     size. *Add row* and *Remove row* change the stack.
   - **Materials:** conductivity, stiffness, Poisson's ratio and thermal
     expansion. Every material a layer uses must be listed.
   - **Heat load and cooling:** the layer that makes the heat, the power, the
     coolant temperature and the film coefficient. A blank film coefficient holds
     the bottom at the coolant temperature.
   - **Mesh and study:** grading, refinement ratio, number of levels and the
     quality limits.
   - **Thermal stress:** untick it for heat flow only, which is much faster.
2. **Name the run.** Results go to `results/<name>/`, so a new name keeps
   earlier results. Changing the name shows that folder's plots, if it has any.
3. **Click Run.** The form is checked first, and a message names any value that is
   wrong. The study then runs in the background and its output streams into the
   log at the bottom right.
4. **Read the results.** When the log says *Finished*, the tabs show the
   convergence, profile, die-top and stress plots. The numbers are in
   `results/<name>/convergence.txt`.
5. **Save as…** writes the form to a parameter file; **Open…** loads one. A saved
   file keeps every value but not the comments.

Closing the window during a run asks first, then stops the study. A CalculiX solve
that has already started finishes on its own.

## The command line

```bash
stackfem geometry params/module.toml   # write the stack as a STEP file, to check it in CAD
stackfem mesh params/module.toml       # mesh level 0 and print its quality, no solve
stackfem run params/module.toml        # the baseline: mesh, check and solve level 0
stackfem study params/module.toml      # every level, then the convergence report
stackfem post params/module.toml       # redo the report and plots from saved results
```

`mesh` and `run` take `--level n` to work on one refinement level. Every command
takes `--out folder`; by default results go to `results/<name>/`, where `name`
comes from the parameter file. `post` reads only the results folder, so plots can
be redone without solving again.

## The parameter file

[params/module.toml](params/module.toml) holds the whole model. Copy it to model a
different stack. Units are mm, W and °C.

| Section | Key | Meaning |
| --- | --- | --- |
| top level | `name` | Names the results folder, `results/<name>/`. |
| `[[layer]]` (one per layer, bottom first) | `name` | Layer name, used in plots and tables. Must be unique. |
| | `material` | A material defined under `[material.*]`. |
| | `size` | Footprint `[width, depth]` in mm. Each layer is a box centred on the z axis. |
| | `thickness` | mm. |
| | `mesh_size` | Element size inside the layer at level 0, mm. Thin layers need a small one. |
| `[material.<name>]` | `conductivity` | W/(m K). |
| | `youngs_modulus` | GPa. Needed only for the stress step. |
| | `poisson` | Poisson's ratio, from 0 to just under 0.5. Stress step only. |
| | `expansion` | Thermal expansion, ppm/K. Stress step only. |
| `[mesh]` | `grading` | Distance, mm, over which the mesh grows from a layer's size to the sizes around it. |
| | `refinement_ratio` | Each study level divides every size by this, above 1. |
| `[quality]` | `min_sicn` | The run stops if any element's scaled Jacobian (SICN) is below this. SICN is 1 for a perfect tetrahedron. |
| | `poor_sicn`, `max_poor_fraction` | The run also stops if more than this fraction of elements are below `poor_sicn`. |
| `[load]` | `source` | The layer that makes the heat, spread evenly through its volume. |
| | `power` | W. |
| | `sink` | Coolant temperature, °C. |
| | `film` | Heat transfer coefficient into the coolant, W/(m² K). Leave it out to hold the bottom at `sink`. |
| `[mechanics]` | (the section) | Turns the stress step on. Delete it to skip stress. |
| | `stress_free` | Temperature, °C, at which the stack has no stress. |
| | `support` | `"flat"`: the baseplate bottom stays flat, as if clamped to a heat sink, but may slide sideways. `"free"`: the whole stack may bow. |
| | `solver` | `"direct"` (the default) or `"iterative"`. See below. |
| `[study]` | `levels` | Number of refinement levels; 1 is the baseline only. Three or more give an extrapolated answer. |

**Which stress solver.** `"direct"` is exact but slow and memory hungry on fine
meshes: on the example's level 2 (266,000 nodes) it ran for over 30 minutes and
used 6.6 GB before it was stopped, where `"iterative"` took about 4 minutes. The
iterative solver leaves errors of about 0.01% in the mean stresses and 0.06% in
displacements, which is close enough for the example study, so the example file
uses it. The heat flow always uses the iterative solver, which matches the direct
one there.

The file is checked as soon as it is read, so a missing material, a bad number or
an unknown `support` or `solver` stops the run before any meshing starts.

## What comes out

```
results/module/
  params.toml             the parameter file the results came from
  form.toml               the form as it was when you clicked Run (window runs only)
  level_0/ ...            one folder per level:
    mesh.msh                the mesh, to open in Gmsh
    module_thermal.inp      the heat-flow deck for CalculiX
    module_thermal.frd      its results, for CalculiX GraphiX (cgx)
    module_thermal.log      CalculiX's output
    module_stress.*         the same for the stress step
    result.npz              nodes, elements, temperatures, displacements and stresses
  summary.csv             one row per level with every tracked result
  convergence.txt         the same as tables, with the extrapolated answers
  convergence.png         each result against element size
  profile.png             temperature up the centre line
  top.png                 temperature over the top of the die
  stress.png              mean and peak stress in each layer
```

`result.npz` is a plain NumPy file. `stackfem.mesh.load(path)` reads it back into
a dict of arrays, for your own plots.

## Results for the example module

20 W in a 3 × 3 mm SiC die on sintered silver, an AlN substrate, SAC305 solder and
a copper baseplate, cooled from below by a liquid at 25 °C (10,000 W/(m² K)). The
stack has no stress at 25 °C, and the baseplate bottom is held flat.

| level | nodes   | max die temperature (°C) | R_th (K/W) | mean solder stress (MPa) | mean die-attach stress (MPa) |
| ----- | ------- | ------------------------ | ---------- | ------------------------ | ---------------------------- |
| 0     | 87,361  | 50.280                   | 1.2640     | 16.64                    | 12.69                        |
| 1     | 150,940 | 50.290                   | 1.2645     | 16.62                    | 12.69                        |
| 2     | 266,166 | 50.296                   | 1.2648     | 16.61                    | 12.68                        |
| 3     | 489,404 | 50.300                   | 1.2650     | 16.60                    | 12.68                        |

Extrapolated to zero element size, the maximum die temperature is 50.305 °C
(observed order 2.67, grid convergence index 0.013%), the mean solder stress is
16.59 MPa (GCI 0.073%) and the mean die-attach stress 12.68 MPa (GCI 0.024%).
The whole study takes about 20 minutes on a laptop. R_th is the rise from the
coolant to the hottest point of the die, per watt.

![Thermal stress by layer](docs/stress.png)

Two things to read carefully:

- **Peak stress grows without limit.** Where a stiff layer ends on a softer one,
  the elastic stress at the edge is infinite in theory. The peak solder stress rises
  from 84 to 104 MPa over the four levels and would keep rising. The study therefore
  tracks the mean stress in each layer, which converges, and shows the peak only to
  say where stress gathers.
- **The largest displacement converges less cleanly** (1.655 to 1.636 µm). The
  iterative solver's error in displacement is close to the change between levels,
  so its fitted order is unreliable. Use `solver = "direct"` when the displacement
  itself matters.

![Temperature along the centre line](docs/profile.png)

## What the model leaves out

- **Shapes.** Every layer is a rectangular box centred on the same axis. Several
  dies, offset parts, copper traces on the substrate and bond wires are not modelled.
- **Heat.** Steady state only, with one heat source spread evenly through its
  layer. Heat leaves only through the baseplate bottom; every other face is
  insulated.
- **Materials.** Properties do not change with temperature.
- **Stress.** Linear elastic and one-way: temperatures cause stress, stress does
  not change temperatures. Real solder and sintered silver creep and yield, so
  these stresses are an upper bound for a first look, not a life prediction.

## Troubleshooting

- **"CalculiX (ccx) was not found."** `ccx` is not on `PATH` and `STACKFEM_CCX`
  is not set. See step 3 of the setup.
- **"ccx failed (exit 3221225781)" on Windows.** That code means a DLL was not
  found: CalculiX's `Library\mingw-w64\bin` folder is missing from `PATH`.
- **"mesh failed the quality checks."** The table in the message shows which layer
  has poor elements. Usually a layer's `mesh_size` is much larger than its
  thickness; make it closer to the thickness, or increase `grading`.
- **A run takes too long.** Use fewer `levels`, set the stress `solver` to
  `"iterative"`, untick *Thermal stress* in the window, or use larger `mesh_size`
  values. Each level has roughly 1.75 times the nodes of the one before.
- **The window shows old plots.** Plots belong to the run name. Change the name, or
  run again.

## Checks

```bash
pytest
```

The tests check the parameter file, the mesh (every layer fills its box, no
element is inverted, node order matches CalculiX), the quality gate, the
extrapolation, and full CalculiX runs against answers worked out by hand: a
three-layer slab with a fixed bottom and with convection, and a slab of one
material heated evenly, which must grow without stress under both supports. The
window's tests check that the form shows a file unchanged and that edits and bad
values reach the parameters. Solver tests are skipped without `ccx`, and window
tests without PySide6. GitHub runs the whole suite on every push.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the code is laid out, and how the
pieces fit together.

## Licence

MIT. See [LICENSE](LICENSE).
