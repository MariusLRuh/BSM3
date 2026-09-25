# Installation

BSM3 is not on PyPI, and neither are the two geometry dependencies it is
validated against. Install it from a checkout, into an environment you control.

BSM3 deliberately declares **no mandatory pip dependencies**. It is designed to
run inside an existing geometry or DAFoam environment whose MPI, PETSc, NumPy,
SciPy, and solver versions are under an administrator's control, and a pip
install must never silently change that stack.

## Validated core stack

The following combination is the one the test suite and the numerical
acceptance runs were executed against.

| Component | Validated version |
| --- | --- |
| Python | 3.12 |
| NumPy | 2.0.2 |
| SciPy | 1.13.1 |
| JAX / jaxlib | 0.4.38 |
| CSDL_alpha | `73a9efd1033016a835779db10a9b9e81ed2254ce` |
| lsdo_function_spaces | `307ad3aabfff31c6fb44ddf51bc0dcc41a60c420` |

```bash
python -m pip install \
  "csdl_alpha @ git+https://github.com/LSDOlab/CSDL_alpha.git@73a9efd1033016a835779db10a9b9e81ed2254ce"

# --no-deps is required: lsdo_function_spaces declares an unpinned CSDL
# dependency that would otherwise replace the validated revision above.
python -m pip install --no-deps \
  "lsdo_function_spaces @ git+https://github.com/LSDOlab/lsdo_function_spaces.git@307ad3aabfff31c6fb44ddf51bc0dcc41a60c420"

# Install BSM3 itself without resolving or building dependencies, so an
# externally managed solver environment is left untouched.
python -m pip install --no-deps --no-build-isolation -e .
```

Both flag choices are load-bearing:

- `--no-deps` on `lsdo_function_spaces` pins CSDL to the validated revision.
- `--no-deps --no-build-isolation` on BSM3 keeps pip from resolving or
  rebuilding anything in the surrounding environment.

## Developer extras

The tests and diagnostics additionally use `pytest`, `gmsh`, `meshio`, and
`pyvista`. Plotting is optional and imported lazily, so a headless environment
that omits `pyvista` still runs the core pipeline and its tests.

## Optional solver environment

DAFoam, OpenFOAM, `mpi4py`, and `petsc4py` are **not** installed by the steps
above and are not needed for surface mesh motion. They come from an existing
sourced solver environment and are only required for the optional aerodynamic
coupling. See [Integrations](integrations.md) for what is and is not exercised.

## Inputs are local files

A run needs a STEP geometry file and a surface mesh file. These are ordinary
local paths that you supply:

```python
inputs = mm.InputFiles(
    geometry_file=Path("/path/to/geometry.stp"),
    surface_mesh_file=Path("/path/to/surface.msh"),
    cache_directory=Path("/path/to/writable/cache"),
)
```

`cache_directory` holds reusable setup data such as baseline projections and
seam identification. The first run populates it; later runs with the same
geometry and mesh are substantially faster. Point it somewhere writable and
outside your source checkout.

### Which example assets ship with the repository

These are tracked and are enough to run the E175 example:

- `bsm3/core/boundary_surface_movement/embraer_175_no_winglets.stp`
- `.../fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.msh`
- `.../embraer_175_quad_dominant_symmetric_no_winglets.msh`
- `.../wall_surface.npz`

Larger volume meshes, refinement-4 walls, and any private CFD case are **not**
tracked. Tests that need them skip automatically when they are absent.

## Documentation is not yet hosted

This site builds from the repository. Build it locally with:

```bash
python -m pip install -r docs/requirements.txt
python -m sphinx -W --keep-going -b html docs /tmp/bsm3-docs-html
```

There is no published Read the Docs deployment yet; `.readthedocs.yaml` is
configured and ready for one.
