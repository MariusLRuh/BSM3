# API reference

`bsm3.mesh_motion` is the intended public namespace and is deliberately
compact. Solver-assembly types, component records, projection callbacks, and
polygon helpers stay internal, because a caller never needs them to deform a
surface mesh.

```python
import bsm3.mesh_motion as mm
```

Everything below is re-exported from that module.

## Public export inventory

This list is the complete supported namespace. A structural test compares it
exactly with `bsm3.mesh_motion.__all__`; semantic descriptions and signatures
are still reviewed against the implementation.

<!-- BEGIN BSM3 PUBLIC EXPORTS -->
- `mm.DerivativeCheck`
- `mm.DistanceWeighting`
- `mm.DistortionPenalty`
- `mm.GeometryModel`
- `mm.InputFiles`
- `mm.MeshMotion`
- `mm.MeshMotionResult`
- `mm.PolygonRegularization`
- `mm.QualityChecks`
- `mm.SurfaceMotion`
- `mm.Visualization`
- `mm.VolumeMotion`
- `mm.run`
<!-- END BSM3 PUBLIC EXPORTS -->

## `run`

```python
mm.run(
    *,
    inputs: InputFiles,
    geometry: GeometryModel,
    motion: MeshMotion,
    recorder: csdl.Recorder,
    aerodynamic_analysis=None,
    aerodynamic_volume_method="elasticity",
) -> MeshMotionResult
```

Evaluates the differentiable mesh-motion model. All arguments are
keyword-only.

`recorder` is the active CSDL recorder, **owned by the caller**. `run` never
starts or stops it, so mesh motion composes inside a larger graph. It is
retained on the result for convenience.

`aerodynamic_analysis` is an optional downstream builder that receives the
selected volume coordinates; `aerodynamic_volume_method` selects which volume
method is handed to it.

## `GeometryModel`

A declaration and binding envelope for the components that move. It does not
constrain how coefficients were parameterized, but any design variables they
depend on must belong to the recorder passed to `run`.

| Method | Purpose |
| --- | --- |
| `add_component(*, name, search_name, deformed_coefficients, free_region=None, projection_name=None, projection_mode="all")` | **The general entry point.** Bind externally produced deformed coefficients. See [External parameterization](external_parameterization.md). |
| `add_lifting_surface(*, name, search_name, pivot_intersection, translation_x=0.0, rotation_y_degrees=0.0, area=None, aspect_ratio=None, reference_area=None, reference_aspect_ratio=None, ...)` | Optional convenience for a wing- or tail-like surface. |
| `add_body(*, name, search_name, diameter_scale=1.0, free_axial_fraction=(0.05, 0.97), projection_name=None)` | Optional convenience for a fuselage-like body. |
| `connect(*, name, driving_component, query_component, search_direction="u", solver_name=None)` | Name the closed intersection curve between two components. |
| `design_variable(name, value, *, lower=None, upper=None, scaler=None)` | Register a design variable on the active recorder and return the CSDL variable. |
| `design_variables` | Mapping of registered design-variable name to CSDL variable. |
| `validate()` | Check the declaration for consistency. |

`add_lifting_surface` and `add_body` are conveniences oriented at the E175
example, not the generic mechanism.

## Input files

`InputFiles(geometry_file, surface_mesh_file, volume_mesh_file=None,
volume_wall_map_file=None, cache_directory=None)`

All are local paths you supply. `volume_mesh_file` and `volume_wall_map_file`
are only needed for the optional volume chain.

## Settings

`MeshMotion` is the top-level settings object:

| Field | Meaning |
| --- | --- |
| `surface` | `SurfaceMotion` — the graph-Laplacian solve |
| `volume` | `VolumeMotion` — optional volume propagation |
| `quality` | `QualityChecks` — which diagnostics run |
| `visualization` | `Visualization` — optional plotting |
| `derivative_check` | `DerivativeCheck` — optional finite-difference sweep |
| `symmetry` | Treat the surface as a half model |
| `symmetry_plane_tolerance` | Tolerance for detecting plane membership |
| `setup_projection_resolution` | Setup-time projection sampling |
| `projection_warm_start_resolution` | Warm-start sampling for reprojection |
| `rebuild_setup_cache` | Ignore and rewrite the cached setup |
| `query_seam_reference` | Use the reference seam for query components |
| `lifting_surface_patch_mode` | Patch selection for lifting surfaces |
| `diagnostic_dump` | Optional diagnostic output path |

The nested types:

- `SurfaceMotion(load_steps, stiffening_exponent, quad_diagonal_weight,
  quad_bracing_mode, distance_weighting, distortion_penalty,
  polygon_regularization)`
- `DistanceWeighting(enabled, beta, length_scale, cap, decay, power,
  seed_intersections)`
- `PolygonRegularization(weight)`
- `DistortionPenalty(weight, mode, area, deviatoric, shear, rotation, normal)`
- `VolumeMotion(mode, load_mode, synchronized_load_steps,
  graph_stiffening_exponent, elasticity_poisson_ratio,
  elasticity_stiffening_exponent, output_directory, write_meshes)`
- `QualityChecks(surface, volume, gmsh_volume_metrics,
  fail_on_surface_inversion, fail_on_volume_inversion)`
- `Visualization(enabled, opacity)`
- `DerivativeCheck(enabled, objective, step_sizes)`

## `MeshMotionResult`

Returned by `run`. Differentiable outputs plus forward diagnostics.

| Attribute | Meaning |
| --- | --- |
| `surface_coordinates` | Final reprojected surface, a CSDL variable |
| `preprojected_surface_coordinates` | Surface before reprojection |
| `initial_surface_coordinates` | Baseline surface |
| `volume_coordinates` | Deformed volume coordinates keyed by method |
| `aerodynamic_outputs` | Optional downstream results |
| `surface_inversion_report` | Inversion diagnostics of the final surface |
| `initial_inversion_report` | Same metric on the untouched input mesh |
| `preprojection_inversion_report` | Same metric before reprojection |
| `surface_quality_report` | Aggregate surface-quality metrics |
| `volume_quality_summary` | Optional volume metrics |
| `surface_fold_count` | Polygons whose area-weighted normal flipped |
| `surface_cell_count` | Cells in the surface |
| `surface_ngon_mode_count` | N-gon hourglass modes present |
| `elapsed_seconds` | Wall-clock time of the solve |
| `surface_mesh`, `volume_mesh` | Loaded mesh objects |
| `input_files`, `geometry`, `recorder` | The inputs that produced this result |

The three inversion reports use the same metric, so any two may be compared
directly. `print_summary()` reports vertex, cell, and n-gon-mode counts;
elapsed time; fold and inversion counts; and, when available,
degenerate-element and minimum-scaled-Jacobian quality fields.

```{note}
Points whose reprojection did not converge are still returned. The reports are
the evidence of solve quality; they are diagnostics, not guarantees.
```
