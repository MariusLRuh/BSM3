# E175 example

The tracked example `examples/e175_surface_deformation.py` deforms an E175
CFD surface mesh and reports its quality. Run it directly:

```bash
python examples/e175_surface_deformation.py
```

It is an ordinary Python script configured by editing values in the file or by
calling `main(...)` with keyword arguments. There is no command-line interface
and no environment-variable configuration.

The script walks the five stages the pipeline performs, in order.

## 1. Choose geometry and mesh files

A STEP body supplies the outer mould line; a surface mesh supplies the nodes
that must follow it.

```python
from pathlib import Path
import tempfile

import csdl_alpha as csdl

import bsm3.mesh_motion as mm

inputs = mm.InputFiles(
    geometry_file=step_file,
    surface_mesh_file=surface_mesh_file,
    cache_directory=Path(tempfile.gettempdir()) / "bsm3_e175_example_cache",
)
```

The example defaults to the tracked triangle wall. To deform the
quad-dominant panel mesh instead, point `surface_mesh_file` at
`embraer_175_quad_dominant_symmetric_no_winglets.msh`. **Nothing else
changes** — it is a path substitution. The same positive
`PolygonRegularization` weight applies to whichever cells the mesh has, and a
triangle-only surface simply has no polygon modes for it to constrain.

## 2. Declare the geometry motion

The recorder is created, started, and stopped **by the caller**. The public
`GeometryModel` and `mm.run` interfaces do not create, start, or stop that
recorder, which is what lets mesh motion compose inside a larger graph. Open
the `try` immediately so a failure in any later stage still stops the recorder.

```python
recorder = csdl.Recorder(inline=True)
recorder.start()
try:
    geometry = mm.GeometryModel()

    wing_shift = geometry.design_variable("wing_shift", 0.0)
    wing_incidence = geometry.design_variable("wing_incidence", 0.0)
    wing_area = geometry.design_variable("wing_area", 70.0)
    tail_incidence = geometry.design_variable("tail_incidence", 0.0)
    fuselage_width = geometry.design_variable("fuselage_width", 1.0)
```

This example uses the **optional** built-in helpers, because they keep the
declaration short and readable. They are not the required entry point: an
external parameterization replaces this stage with
[`add_component`](external_parameterization.md), and stages 3 to 5 are
identical either way.

```python
    geometry.add_lifting_surface(
        name="wing",
        search_name="wing",
        pivot_intersection="wing_root",
        translation_x=wing_shift,
        rotation_y_degrees=wing_incidence,
        area=wing_area,
        reference_area=70.0,
        reference_aspect_ratio=8.4,
    )
    geometry.add_lifting_surface(
        name="tail",
        search_name="HT",
        pivot_intersection="tail_root",
        rotation_y_degrees=tail_incidence,
        projection_name="horizontal_tail",
    )
    geometry.add_body(
        name="fuselage",
        search_name="fuselage",
        diameter_scale=fuselage_width,
    )
```

`connect` names the closed intersection curve between two components. The
`pivot_intersection` above refers to one of these by name.

```python
    geometry.connect(
        name="wing_root",
        driving_component="wing",
        query_component="fuselage",
    )
    geometry.connect(
        name="tail_root",
        driving_component="tail",
        query_component="fuselage",
    )
```

## 3. Choose mesh-motion and quality settings

```python
    motion = mm.MeshMotion(
        surface=mm.SurfaceMotion(
            load_steps=2,
            stiffening_exponent=1.5,
            distance_weighting=mm.DistanceWeighting(
                enabled=True,
                beta=5.0,
                length_scale=10.0,
                decay="exp",
            ),
            polygon_regularization=mm.PolygonRegularization(weight=0.3),
        ),
        quality=mm.QualityChecks(surface=True),
        symmetry=True,
    )
```

`symmetry=True` declares that the surface is a half model about the symmetry
plane. See [Background](background.md) for what each setting controls.

## 4. Run the differentiable model

```python
    result = mm.run(
        inputs=inputs,
        geometry=geometry,
        motion=motion,
        recorder=recorder,
    )
finally:
    recorder.stop()
```

## 5. Inspect the result

```python
result.print_summary()
```

`print_summary` reports vertex, cell, and n-gon-mode counts; elapsed time; fold
and inversion counts; and, when available, degenerate-element and minimum
scaled-Jacobian quality fields. The arrays are on the result object:
`result.surface_coordinates` is the final reprojected surface as a CSDL
variable, with `initial_surface_coordinates` and
`preprojected_surface_coordinates` alongside it for comparison, plus the
inversion and quality reports. See the [API reference](api.md).

## Deformation scale

The example interpolates the whole design point with a single
`deformation_scale`, so one number moves every target coherently. Its default
is small and deliberate: it is the largest coherent scale measured to leave the
sliver-sensitive quad-dominant panel with no newly inverted element. Raising it
is reasonable on the triangle wall and should be checked against the inversion
report on the quad panel.
