# Candidate retained-file manifest

This is the non-destructive M0.2 manifest. It is an input to M3.1, not a
deletion list. Nothing outside this document is safe to delete until every
declared root has an end-to-end test and M3.1 proves the resulting boundary.

## M1.5 mesh-generation disposition

M1.5 adopts no mesh-generation module. The core already imports none of the
candidate Gmsh/OCC scripts, while the only credible general STEP-to-surface
path is an untracked circular pair: `gmsh_occ_oml_surface_mesh.py` (2,475 LOC)
and `smooth_existing_tip_cap.py` (2,283 LOC). Adopting 4,758 untested LOC would
expand the release surface without strengthening the existing core boundary.

Root M below therefore remains a **local candidate used to measure the M0
closure**, not a commitment to retain or release those files. M3 must revisit
mesh generation with a minimal `STEP -> surface mesh` API, a deterministic
small STEP fixture, and an end-to-end topology/quality test before any code is
adopted into `bsm3.meshgen`.

## Static Python closure

The trace parses every Python file under `bsm3/`, follows absolute and relative
imports that resolve to another `bsm3` module, follows package `__init__.py`
imports, and includes imports nested inside functions and conditionals. It does
not infer imports whose module name is computed at runtime or any file opened
through a runtime path.

Roots and abbreviations:

| Key | Root | Files | Current LOC |
|---|---|---:|---:|
| S | STEP-to-surface motion: `bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py` | 42 | 20,895 |
| D | DAFoam boundary: `bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py` | 45 | 23,066 |
| P | VortexAD/panel: `bsm3/core/boundary_surface_movement/e175_panel_opt.py` | 42 | 21,066 |
| V | Volume-motion boundary: `bsm3/core/boundary_surface_movement/geometry_volume_mpi.py` | 1 | 378 |
| M | Mesh generation: `bsm3/core/boundary_surface_movement/gmsh_occ_oml_surface_mesh.py` | 41 | 23,578 |
| L | Derivative ladder: `bsm3/core/boundary_surface_movement/e175_derivative_ladder.py` | 47 | 24,162 |

The M1.3 union is **51 files / 29,465 LOC**, a net decrease of **3 files / 3,472
LOC** from the Turn-4 snapshot. The three whole-file removals account for 2,101
LOC; the remainder reflects the partial-file cleanup and intervening accepted
changes in the retained closure. The original snapshot
reproduced Claude's 54-file closure. The five-line difference from Claude's
32,932-LOC result is the net effect of Turn 4's explicit trusted-pickle public
API. Counts use `len(path.read_text().splitlines())`, so they are snapshots,
not acceptance thresholds.

| Retained Python file | Root(s) |
|---|---|
| `bsm3/__init__.py` | S, D, P, M, L |
| `bsm3/component_parameters.py` | S, D, P, M, L |
| `bsm3/core/__init__.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/__init__.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py` | D, L |
| `bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py` | S |
| `bsm3/core/boundary_surface_movement/constraints.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/current_graph_solve.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/dafoam_csdl.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/e175_derivative_ladder.py` | L |
| `bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py` | S, D, P, L |
| `bsm3/core/boundary_surface_movement/e175_mesh_motion_pipeline.py` | S, D, P, L |
| `bsm3/core/boundary_surface_movement/e175_panel_opt.py` | P |
| `bsm3/core/boundary_surface_movement/elasticity.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/forward_only_fd_checker.py` | L |
| `bsm3/core/boundary_surface_movement/free_region.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/geometry.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/geometry_volume_backend.py` | D, L |
| `bsm3/core/boundary_surface_movement/geometry_volume_mpi.py` | S, D, P, V, M, L |
| `bsm3/core/boundary_surface_movement/geometry_volume_operation.py` | D, L |
| `bsm3/core/boundary_surface_movement/gmsh_occ_oml_surface_mesh.py` | M |
| `bsm3/core/boundary_surface_movement/graph_distance.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/intersections.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/load_stepping.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/motion.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/ngon_affine.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/projection.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/quadratic_distortion.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/quality.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/rbf.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py` | D, L |
| `bsm3/core/boundary_surface_movement/smooth_existing_tip_cap.py` | M |
| `bsm3/core/boundary_surface_movement/spd_solve_custom_op.py` | S, D, P, M, L |
| `bsm3/core/boundary_surface_movement/volume_mesh_motion.py` | S, D, P, M, L |
| `bsm3/core/projections/function_set_closest_distance_custom_op.py` | S, D, P, M, L |
| `bsm3/core/projections/function_set_evaluation_custom_op.py` | S, D, P, M, L |
| `bsm3/core/projections/function_set_projection_custom_op.py` | S, D, P, M, L |
| `bsm3/core/projections/orthogonality_projection_numpy.py` | S, D, P, M, L |
| `bsm3/core/projections/warm_start_candidate_projection_numpy.py` | S, D, P, M, L |
| `bsm3/core/projections/warm_start_projections.py` | S, D, P, M, L |
| `bsm3/core/weighting_functions.py` | S, D, P, M, L |
| `bsm3/plotting.py` | S, D, P, M, L |
| `bsm3/preprocessing/__init__.py` | S, D, P, M, L |
| `bsm3/preprocessing/components.py` | S, D, P, M, L |
| `bsm3/preprocessing/gmsh.py` | S, D, P, M, L |
| `bsm3/preprocessing/intersections.py` | S, D, P, M, L |
| `bsm3/preprocessing/mesh_io.py` | S, D, P, M, L |
| `bsm3/preprocessing/movement.py` | S, D, P, M, L |
| `bsm3/preprocessing/quad_conversion.py` | S, D, P, M, L |
| `bsm3/preprocessing/stl.py` | S, D, P, M, L |
| `bsm3/preprocessing/symmetry.py` | S, D, P, M, L |

The apparently broad root membership is real: importing `bsm3` and the
boundary-surface package executes their `__init__.py` re-export surfaces. The
volume root itself is a leaf, but it is also imported by the other roots
through those re-exports.

## Runtime data dependencies

Static Python imports do not discover these. "Local" means the API remains
supported but the file must be supplied by the user and must not be added to
the curated release assets merely to make CI pass.

| File or path contract | Root(s) | Disposition/mechanism |
|---|---|---|
| `bsm3/core/boundary_surface_movement/embraer_175_no_winglets.stp` | S, D, P, M, L | Curated, tracked STEP input passed to `lsdo_function_spaces.import_file_patched`. |
| `bsm3/core/boundary_surface_movement/fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.msh` | S, V | Curated, tracked triangle-wall regression asset. |
| `bsm3/core/boundary_surface_movement/fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.volume_map.npz` | V | Curated, tracked wall-map regression asset; no matching committed volume mesh is required in M1. |
| `bsm3/core/boundary_surface_movement/embraer_175_quad_dominant_symmetric_no_winglets.msh` | P, S | Curated, tracked quad regression/panel candidate. |
| `bsm3/core/boundary_surface_movement/wall_surface.npz` | S | Curated, tracked mixed-N-gon regression asset, **non-executable** since M1.8. It loads through the generic `import_mesh` suffix dispatch with `allow_pickle=False`, and the former trusted legacy pickle of the same base name was converted exactly and deleted. The E175 pipeline's internal legacy pickle branch is gone; no curated asset or retained pipeline loads a pickle. |
| `fluent_R4_tet_euler_volume_mesh/e175_fluent_R4_aircraft_wall_tri.msh` | S, L | Local current-driver input, resolved from `MODEL_FILES`; absent checkouts skip its integration assertion. |
| `fluent_R4_tet_euler_volume_mesh/e175_fluent_R4_tet_euler_volume.msh` | S, V, L | Local 100.9 MB volume input; explicitly excluded from curated assets. |
| `fluent_R4_tet_euler_volume_mesh/e175_fluent_R4_aircraft_wall_tri.volume_map.npz` | S, V, L | Local wall-to-volume map. |
| `openvsp_euler_volume_mesh/e175_openvsp_aircraft_wall.msh` | D, L | Currently tracked legacy DAFoam wall input; migrate to the local-path contract before M3. |
| `openvsp_euler_volume_mesh/e175_euler_volume.msh` | D, V, L | Currently tracked legacy 45 MB volume input; migrate to the local-path contract before M3. |
| `openvsp_euler_volume_mesh/e175_openvsp_aircraft_wall.volume_map.npz` | D, V, L | Currently tracked legacy wall map; migrate with the DAFoam volume input before M3. |
| `embraer_175_panel_quad_dominant_high_quality.msh` | P | Local default VortexAD mesh. M1.7 must either use the curated quad mesh or document why this separate mesh is required. |
| `stored_files/imports/embraer_175_no_winglets_stored_import.pickle` | S, D, P, L | Optional/generated `lsdo_function_spaces` STEP-import cache selected by filename convention; not visible to Python import tracing. |
| `_setup_cache_<mesh>_<geometry>_nu<N>_sym<B>.npz` | S, D, P, L | Generated projection/intersection cache. Selection depends on configured paths, mtimes, options, and a code signature. It is disposable, not a retained source asset. |
| `bsm3/core/projections/refitted_fun_set.pkl` | S, L | **Untracked local artifact only — no longer a retained default dependency.** Until M1.8 the retained `warm_start_projections.DEFAULT_FUN_SET_PATH` pointed at this path, so the package had an implicit executable-pickle default. That constant is deleted and the consolidated `load_function_set_from_trusted_pickle(pickle_path)` takes a mandatory path, so no retained code reaches this file unless a caller names it. It remains an untracked local file used by untracked drivers; it is not curated, not tracked, and not required by any tracked test. |
| DAFoam/OpenFOAM case directory | D, L | Local directory selected by `CASE.case_directory` or `DAFOAM_CASE_DIRECTORY`; contains `constant/polyMesh`, dictionaries, and solver state. Never a repository asset. |
| Mesh/result output directories and `.msh`, `.npz`, `.json` products | S, D, P, V, M, L | Runtime outputs derived from configured paths; never inputs to the retained-file closure unless a test explicitly promotes one to a fixture. |

## Dependencies and dispatch invisible to a file-only closure

| Mechanism | Location | What M3.1 must prove |
|---|---|---|
| Computed imports | `e175_mesh_motion_pipeline._setup_code_signature` | Six module names are passed to `importlib.import_module`: preprocessing movement/intersections, three projection modules, and boundary-surface intersections. They are in the current union for other reasons, but must remain tied to this cache signature after refactoring. |
| Lazy optional Python imports | `e175_panel_opt`, `dafoam_csdl`, `geometry_volume_mpi`, `cfd_mesh_dafoam_analysis`, `run_dafoam_gmsh`, `preprocessing.gmsh`, `volume_mesh_motion` | Runtime branches require `VortexAD`, `dafoam`, `petsc4py`, `mpi4py`, `meshio`, or `gmsh`. Import-only tests cannot establish that these branches work. |
| Package re-exports | `bsm3/__init__.py`, `bsm3/preprocessing/__init__.py`, `bsm3/core/boundary_surface_movement/__init__.py` | `from package import Name` may resolve a re-export rather than a same-named module. M3.1 must test the public import surface and not infer module ownership from the imported string alone. |
| String/config dispatch | `SurfaceMotionConfig`, `VolumeMotionConfig`, graph bracing, projection, RBF, and mesh-quality paths | Modes such as `graph`, `off`/`elasticity`, `final`/`synchronized`, bracing modes, projection modes, and RBF fit modes select code without importing it. Each supported production value needs behavioral coverage. |
| File-suffix dispatch | mesh, STEP, volume-map, and trusted polygon readers | `.msh`, `.stl`, `.npz`, STEP, and explicitly trusted pickle paths select parsers at runtime. Tests must cover each retained format. Generic `import_mesh` deliberately does not dispatch pickle. |
| External commands and environment | `run_dafoam_gmsh`, DAFoam drivers, derivative ladder | `gmshToFoam`, `checkMesh`, OpenFOAM/DAFoam environment setup, MPI launch, `DAFOAM_CASE_DIRECTORY`, and ladder environment variables are outside the AST closure. |
| Generated cache signatures | `e175_mesh_motion_pipeline` and `lsdo_function_spaces` | Cache reuse is controlled by names, mtimes, settings, and serialized metadata. Tests must pass from an empty cache and from a valid warm cache; generated caches must not become hidden release requirements. |

## Repository support boundary

The 54-file count intentionally covers production Python under `bsm3/`, not
tests, packaging, CI, or collaboration records. A release assembled in M3 must
also retain `setup.py`, `README.md`, `LICENSE.txt`, `.github/workflows/actions.yml`,
`requirements-ci.txt`, `pytest.ini`, `ruff.toml`, `tests/`, and
`docs/overhaul/`. Their exact file list will change during M1, so M3.1 must
freeze and validate that support manifest after the API and tests stabilize.
