# Curated E175 assets for the overhaul

The M0/M1 surface workflows use a small local asset set. Paths are relative to
the repository root. No volume mesh is required for M1.

| Purpose | Path | Approximate size |
|---|---|---:|
| STEP geometry | `bsm3/core/boundary_surface_movement/embraer_175_no_winglets.stp` | 0.9 MB |
| Triangle CFD wall | `bsm3/core/boundary_surface_movement/fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.msh` | 1.9 MB |
| R1 wall-to-volume metadata | `bsm3/core/boundary_surface_movement/fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.volume_map.npz` | 1.3 MB |
| Quad-dominant panel mesh | `bsm3/core/boundary_surface_movement/embraer_175_quad_dominant_symmetric_no_winglets.msh` | 1.1 MB |
| Mixed N-gon CFD wall | `bsm3/core/boundary_surface_movement/wall_surface.pkl` | 2.7 MB |

Total size is approximately 7.9 MB. The mixed N-gon asset contains polygon5
through polygon9 cells, including 28,190 six-sided cells. The similarly named
`embraer_175_hexagonal_symmetric_no_winglets.msh` is not an N-gon surface mesh;
it contains triangles and quads and is therefore not part of this set.

The pickle is a trusted legacy local asset. It must not be loaded from an
untrusted source. A later cleanup may replace it with a non-executable polygon
container while preserving the same coordinates and connectivity.

Volume meshes remain user-supplied local inputs. This keeps the curated set
well below the 50 MB budget while retaining the volume-motion and DAFoam API
boundaries for later integration validation.
