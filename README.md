# BSM3

BSM3 contains differentiable geometry, boundary-surface mesh motion,
tetrahedral volume mesh motion, and an experimental CSDL/DAFoam coupling.

The current E175 workflows are:

- `bsm3.core.boundary_surface_movement.cfd_mesh_movement_test`: geometry,
  surface motion, volume motion, quality diagnostics, and visualization.
- `bsm3.core.boundary_surface_movement.cfd_mesh_dafoam_analysis`: the same
  geometry/mesh pipeline followed by DAFoam outputs such as CL and CD.

Both drivers expose explicit Python configuration blocks for the STEP geometry,
surface mesh, volume mesh, geometry variables, mesh-motion settings, and flow
configuration. There is no command-line or environment-variable configuration
inside these drivers.

## Installation in an existing solver environment

BSM3 deliberately installs no dependencies automatically. This prevents a pip
installation from changing an externally managed DAFoam, MPI, or PETSc stack.

```bash
python -m pip install --no-deps --no-build-isolation -e .
```

For the TSCC/DAFoam prerequisite audit and installation procedure, see
[HPC_DAFOAM_INSTALL.md](HPC_DAFOAM_INSTALL.md).

## Running

Run the deformation pipeline:

```bash
python -m bsm3.core.boundary_surface_movement.cfd_mesh_movement_test
```

Run the tests:

```bash
python -m pytest tests -q
```

The DAFoam driver requires a sourced DAFoam environment and an OpenFOAM case
directory configured in `cfd_mesh_dafoam_analysis.py`.

## License

BSM3 is licensed under the GNU Lesser General Public License v3.0 or later.
