# Curated E175 assets for the overhaul

The M0/M1 surface workflows use a small local asset set. Paths are relative to
the repository root. No volume mesh is required for M1.

| Purpose | Path | Approximate size |
|---|---|---:|
| STEP geometry | `bsm3/core/boundary_surface_movement/embraer_175_no_winglets.stp` | 0.9 MB |
| Triangle CFD wall | `bsm3/core/boundary_surface_movement/fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.msh` | 1.9 MB |
| R1 wall-to-volume metadata | `bsm3/core/boundary_surface_movement/fluent_R1_tet_euler_volume_mesh/e175_fluent_R1_aircraft_wall_tri.volume_map.npz` | 1.3 MB |
| Quad-dominant panel mesh | `bsm3/core/boundary_surface_movement/embraer_175_panel_quad_dominant_high_quality.msh` | 1.3 MB |
| Mixed N-gon CFD wall | `bsm3/core/boundary_surface_movement/wall_surface.npz` | 2.2 MB |

Total size is approximately 7.6 MB. The panel asset replaces the former
quad-dominant example mesh, whose baseline contained 114 inverted elements.
The replacement contains 13,262 vertices, 2,804 triangles, and 11,858 quads;
its curated SHA-256 is
`92feeeda05905a13d23a18c863e76b9596773beccb021148cc2d4e7016cd733c`.
The mixed N-gon asset contains polygon5
through polygon9 cells, including 28,190 six-sided cells. The similarly named
`embraer_175_hexagonal_symmetric_no_winglets.msh` is not an N-gon surface mesh;
it contains triangles and quads and is therefore not part of this set.

The mixed N-gon wall is a **non-executable** NumPy archive, loaded through the
generic `bsm3.preprocessing.import_mesh` with `allow_pickle=False`. It holds
exactly three non-object arrays:

- `vertices`: float64, shape `(79207, 3)`;
- `connectivity`: flattened int64 node IDs in the original face order,
  shape `(239385,)`;
- `offsets`: int64, shape `(40707,)`, starting at zero, where
  `connectivity[offsets[i]:offsets[i + 1]]` is original face `i`.

It replaces the former trusted legacy pickle of the same base name
(2,863,763 bytes, sha256
`34165debb2a3dde52dd7380cc1d91e99d829db96042858f710154b201f055b4d`), which was
converted once in M1.8 and deleted. The conversion is exact: the decoded arrays
hash to `76ceaadd…` (vertices), `971e53f7…` (connectivity), and `eff2e0fe…`
(offsets), giving 40,706 faces with widths 3:5, 4:565, 5:7,891, 6:28,190,
7:3,927, 8:126, 9:2, node IDs 0 through 79,206, and 14,720 adjacent width
transitions that evidence the preserved source order. No curated asset requires
pickle to load.

Volume meshes remain user-supplied local inputs. This keeps the curated set
well below the 50 MB budget while retaining the volume-motion and DAFoam API
boundaries for later integration validation.
