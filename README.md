# BSM3

BSM3 performs **differentiable boundary-surface mesh motion**. Given a CAD
outer mould line and a surface mesh that must follow it, BSM3 moves every mesh
node so the mesh stays valid while the geometry deforms, through a CSDL graph
so the whole map carries analytic derivatives.

It also provides tetrahedral volume-mesh motion and an optional CSDL/DAFoam
coupling.

## Quickstart

`bsm3.mesh_motion` is the intended entry point and is deliberately small.

```python
from pathlib import Path

import csdl_alpha as csdl

import bsm3.mesh_motion as mm

recorder = csdl.Recorder(inline=True)
recorder.start()
try:
    geometry = mm.GeometryModel()
    # Either bring your own deformed coefficients:
    #     geometry.add_component(name=..., search_name=...,
    #                            deformed_coefficients=...)
    # or use the optional built-in helpers, as the E175 example does.

    result = mm.run(
        inputs=mm.InputFiles(
            geometry_file=Path("geometry.stp"),
            surface_mesh_file=Path("surface.msh"),
            cache_directory=Path("/tmp/bsm3_cache"),
        ),
        geometry=geometry,
        motion=mm.MeshMotion(quality=mm.QualityChecks(surface=True)),
        recorder=recorder,
    )
finally:
    recorder.stop()

result.print_summary()
```

The recorder is owned by the caller: BSM3 never starts or stops it.

A complete, runnable example is tracked at
[`examples/e175_surface_deformation.py`](examples/e175_surface_deformation.py).

## Documentation

The documentation source is in [`docs/`](docs/). There is no hosted
deployment yet. Build it locally:

```bash
python -m pip install -r docs/requirements.txt
python -m sphinx -W --keep-going -b html docs /tmp/bsm3-docs-html
```

It covers installation, the E175 example, the external-parameterization
contract, the public API, background, and integration status.

## Installation

BSM3 is not on PyPI, and neither are its two geometry dependencies. It
deliberately installs no dependencies automatically, so a pip install cannot
change an externally managed DAFoam, MPI, or PETSc stack.

The validated stack is Python 3.12 with NumPy 2.0.2, SciPy 1.13.1, and JAX
0.4.38, against these exact revisions:

```bash
python -m pip install \
  "csdl_alpha @ git+https://github.com/LSDOlab/CSDL_alpha.git@73a9efd1033016a835779db10a9b9e81ed2254ce"

# --no-deps keeps the validated CSDL revision above from being replaced.
python -m pip install --no-deps \
  "lsdo_function_spaces @ git+https://github.com/LSDOlab/lsdo_function_spaces.git@307ad3aabfff31c6fb44ddf51bc0dcc41a60c420"

python -m pip install --no-deps --no-build-isolation -e .
```

See [docs/src/getting_started.md](docs/src/getting_started.md) for details, and
[HPC_DAFOAM_INSTALL.md](HPC_DAFOAM_INSTALL.md) for the TSCC/DAFoam prerequisite
audit.

## Running

```bash
python examples/e175_surface_deformation.py
python -m pytest tests -q
```

DAFoam, OpenFOAM, `mpi4py`, and real MPI are optional integrations that need an
existing sourced solver environment and a case you supply. They are not run in
the standard test suite.

## License

BSM3 is licensed under the GNU Lesser General Public License v3.0 or later.
