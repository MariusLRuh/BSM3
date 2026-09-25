# BSM3

BSM3 performs **differentiable boundary-surface mesh motion**. Given a CAD
outer mould line and a surface mesh that must follow it, BSM3 moves every mesh
node as the geometry deforms, carries analytic derivatives through the CSDL
graph, and reports mesh-quality and inversion diagnostics so validity is
checked rather than guaranteed.

The pipeline is:

```text
geometry parameterization
    -> deformed component coefficients
    -> intersection curves between components
    -> graph-Laplacian surface motion with regularization
    -> reprojection onto the deformed outer mould line
    -> quality and inversion diagnostics
    -> optional volume-mesh motion
```

`bsm3.mesh_motion` is the intended entry point and is deliberately small: input
files, a `GeometryModel` describing what moves, a `MeshMotion` settings object
describing how the mesh follows, and `run` to evaluate it.

```python
import bsm3.mesh_motion as mm

result = mm.run(
    inputs=mm.InputFiles(
        geometry_file=step_path,
        surface_mesh_file=surface_path,
        cache_directory=cache_path,
    ),
    geometry=geometry,
    motion=mm.MeshMotion(quality=mm.QualityChecks(surface=True)),
    recorder=recorder,
)
result.print_summary()
```

## Where to start

- **[Installation](src/getting_started.md)** — the validated Python 3.12
  dependency stack and the install flags that protect an existing solver
  environment.
- **[E175 example](src/examples.md)** — the five-stage workflow, based on the
  tracked `examples/e175_surface_deformation.py`.
- **[External parameterization](src/external_parameterization.md)** — the
  generic contract: bring your own differentiable coefficients.
- **[API reference](src/api.md)** — the public `bsm3.mesh_motion` surface.
- **[Background](src/background.md)** — what each pipeline stage does and why.
- **[Integrations and troubleshooting](src/integrations.md)** — honest status
  of DAFoam/OpenFOAM, MPI, VortexAD, mesh generation, and assets.

```{toctree}
:maxdepth: 2
:hidden:

src/getting_started
src/examples
src/external_parameterization
src/api
src/background
src/integrations
```
