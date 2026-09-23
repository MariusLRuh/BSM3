# Planning prompt for Claude — Turn 31 (M1.7a usability rejection)

Paste this entire prompt into Claude at the repository root.

---

Read `docs/overhaul/PLAN.md`, `docs/overhaul/LOG.md`, and the implementation
in commits `476b10d` and `a9c2830`.

## Ruling supplied by the user

M1.7a is **REJECTED on usability/API-design grounds**. The implementation is a
reasonable first attempt and its numerical results remain useful, but the
example is too low-level and cluttered to serve as the flagship public API.
Do not spend this turn deciding whether to accept it or rerunning the expensive
clean-clone suite. Treat the following as requirements for the corrective
implementation:

1. **No CLI.** Remove `argparse`, `argv`, and command-line switches. Every input
   must be visible and directly editable in the main script.
2. **Hide mechanics behind appropriate helpers.** Users should provide
   high-level geometry and mesh-motion inputs. They should not have to read or
   write coefficient-builder callbacks such as `_wing_coefficients`, nor
   diagnostics mechanics such as `_surface_cells`, `_polygon_normals`, or fold
   counting. Decide which abstractions belong in the public library and which
   aircraft-specific assembly, if any, belongs in a small example helper. Do
   not merely rename or move 500 lines of complexity out of sight.
3. **Make the five pipeline steps unmistakable in executable code**, not only
   in the module docstring. The main script should read top-to-bottom as five
   short, visibly separated stages.
4. **No dataclass definitions in the run script.** Prefer returning the public
   pipeline result directly. If a reusable result abstraction is genuinely
   needed, it belongs in the library rather than the example.
5. **No `mesh_kind` input.** The user supplies a surface-mesh `Path` directly.
   Selecting the triangle or quad mesh is done by changing that path. Any
   topology-dependent behavior must be derived from the loaded mesh or exposed
   as an explicit high-level numerical setting, not inferred from a string
   label such as `"tri"` or `"quad"`.
6. **Substantially simplify the import and configuration surface.** The current
   block of roughly twenty imported classes is overwhelming. Design a small,
   intuitive public entry surface rather than teaching users the internal
   configuration object graph.
7. **Public configuration classes should not use the `Config` suffix.** This is
   a clean-break API, so do not retain deprecated aliases merely for
   compatibility. Inspect name collisions before proposing exact replacements.
8. **Replace opaque names.** In particular,
   `DeclarativeGeometryParameterization` is not acceptable: “declarative” does
   not communicate anything useful to the user. Choose a short name that says
   what the object contains or does. Review the other exposed names under the
   same standard rather than changing only this one.

These requirements supersede Turn 30's “all of `bsm3/` is prohibited” rule.
The example has exposed a public-API design problem, so the corrective turn may
change library code and tests. The user's earlier clean-break decision still
applies: avoid compatibility aliases and one-valued legacy fields.

## Your task this turn: design and issue the correction, do not implement it

Claim `## Turn 31` by appending to `docs/overhaul/LOG.md`. Perform a careful
static design audit of the current example and every public type/function it
uses. Then:

1. Record the user rejection and your design conclusions in `LOG.md`.
2. Update `PLAN.md` so M1.7a remains open and its acceptance criteria include
   all eight requirements above. Preserve the remaining order: corrected
   M1.7a, M1.6 slices 2-3, M1.8, then full M1.7 acceptance.
3. Replace this file with the next concrete Codex implementation prompt.

For this planning/review turn you may edit only:

```
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Do not edit implementation files yourself.

## Required design work before writing the Codex prompt

Trace the current public configuration/result graph and all references to every
class you propose renaming. Resolve collisions explicitly—for example, the
repository may already have runtime objects whose names would collide with a
configuration class after dropping `Config`. Choose a coherent vocabulary,
not a collection of local substitutions.

Design the smallest high-level interface that allows the main script to state:

- STEP geometry path;
- surface-mesh path;
- cache path;
- high-level wing, tail, and fuselage design values;
- component identities and independent intersections, without callback boilerplate;
- graph-Laplacian settings and optional n-gon regularization;
- surface-only execution, headless output, and quality checks.

The example must still use the **general API**. E175-specific knowledge must
not be smuggled into the core pipeline. If reusable component motions need
named helpers (for example, lifting-surface planform/rigid motion or body
diameter scaling), design those as general concepts with high-level inputs.
The user should not have to manipulate component coefficient arrays, compute
intersection-derived pivots manually, enumerate polygon connectivity, or
implement Newell normals in the example.

The five executable stages should be recognizable at a glance, approximately:

1. define input paths and design values;
2. describe components/intersections using the high-level geometry API;
3. select surface-motion and quality behavior;
4. build/run the model;
5. inspect or print the public result/diagnostics.

This outline is descriptive, not a mandate to preserve current class names or
the current nested configuration hierarchy.

## Requirements for the corrective Codex prompt

The generated prompt must include:

- the exact proposed public names and signatures, including every `Config`
  rename and the replacement for `DeclarativeGeometryParameterization`;
- a literal per-file allowlist based on actual reference tracing, not a guessed
  file count;
- explicit deletion of the CLI, `mesh_kind`, example-local dataclass, callback
  builders, and polygon-normal/connectivity implementations;
- a readability acceptance check for the example, including a maximum import
  count or similarly mechanical clutter bound that you first verify is
  achievable;
- a check that the five executable stages are visibly labeled and ordered;
- tests that configure the example through paths/high-level values and retain
  the tri end-to-end zero-fold/zero-inversion gate;
- a real quad-path test or run showing that topology is selected by the file
  and nonzero n-gon regularization still executes;
- derivative and M1.4 guards with unchanged values;
- clean-clone execution and post-run clean-status checks;
- a stop rule for any abstraction that would encode E175 assumptions in the
  generic pipeline, any unresolved public-name collision, numerical drift, or
  need to widen the audited allowlist.

Do not prescribe deprecated aliases, a temporary dual API, or an example-only
facade that leaves the confusing public API intact. This corrective slice may
be larger than the original two-file example turn because the user's feedback
is specifically about the public API. Keep it bounded to the reachable surface
needed by this example and do not absorb M1.6 slices 2-3 or M1.8.

Close Turn 31 after writing the corrective Codex prompt. Report the proposed
new vocabulary prominently so the user can challenge it before implementation.
