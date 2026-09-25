# Claude Turn 75 — review M4.2

Codex implemented M4.2 in `027a890` and recorded the handoff in the following
documentation commit. Review independently; do not accept Codex's measurements
without reproducing the relevant gates, and do not implement unrelated work in
the same turn.

## Review boundary

Implementation base: `699ad9a`

Implementation commit: `027a890`

The implementation commit must contain exactly these 11 paths:

```text
bsm3/core/boundary_surface_movement/panel_aerodynamics.py
bsm3/core/boundary_surface_movement/fuel_burn.py
bsm3/core/boundary_surface_movement/__init__.py
bsm3/mesh_motion.py
examples/e175_fuel_burn_optimization.py
tests/test_panel_aerodynamics.py
tests/test_fuel_burn.py
docs/src/integrations.md
docs/src/api.md
docs/src/examples.md
requirements.txt
```

The handoff commit may change only:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/MANIFEST.md
docs/overhaul/CODEX_NEXT.md
```

Preserve the user's eight modified tracked files and 393 untracked entries.
The expected hashes are:

```text
dirty diff:     981318561a10dff8e9d723540902b6d2560875b29656a0b59f0803cbff116177
untracked list: c38fd93dc32ecf7f927fc612c1079bd9786c19f6c1f74b4f8e69d28aaa44da60
```

## Review questions

1. **Pinned API.** Confirm from the official repository, without installing or
   running VortexAD, that revision
   `8c5bc86fda5fa1e359fecde24c6c6e8527c773b5` exports `PanelMethod`,
   `TE_detection`, and `find_cell_adjacency`, and that the adapter's constructor,
   grid insertion, output declaration, and evaluation calls match that revision.
2. **Optional boundary.** Confirm importing `bsm3.mesh_motion` and
   `bsm3.core.boundary_surface_movement` does not import or require VortexAD.
   The actionable error must arise only when `build_panel_aerodynamics` is
   called. `setup.py`, `requirements-ci.txt`, and the workflow must be unchanged.
3. **Public-result discipline.** Confirm the adapter reads only public
   `MeshMotionResult` fields, leaves recorder ownership with the caller,
   validates projection convergence and the intersection/reprojection
   partition, supports triangle/quad panels only, and does not reach into
   private setup/system objects.
4. **Real API assumptions.** Trace the pinned implementation far enough to
   decide whether the baseline-connectivity, duplicate-node, trailing-edge,
   output-name, scalar-shape, and `reuse_AIC=True` assumptions are honest. Pay
   particular attention to whether a full symmetric E175 mesh and its mixed
   triangle/quad blocks are accepted exactly as passed.
5. **Fuel model.** Re-derive the Breguet expression, signs, units, standard
   gravity value, and derivative direction. Decide whether returning fuel
   **weight** in newtons is sufficiently clear and whether the illustrative
   mission/parasite-drag constants are labelled strongly enough.
6. **Composed derivative.** Inspect and run the fake-solver test. It must carry
   the mesh-shape design amplitude through panel `CL`/`CDi`, total drag, and
   `compute_fuel_burn`, then compare the fuel scalar's analytic derivative with
   centered finite differences. A test ending at an arbitrary aerodynamic
   scalar is not sufficient.
7. **Example contract.** Confirm the example has five clear stages, no CLI or
   local dataclasses, uses only the public `mm` API, keeps the caller-owned
   recorder active through the panel/fuel graph, leaves
   `derivative_check.enabled` false, registers the lift constraint and fuel
   objective explicitly, and fails actionably when VortexAD is absent.
8. **Documentation.** Confirm the API export inventory remains exact and the
   integrations/example pages make no claim that a real VortexAD solve or
   geometry-to-fuel optimization has been executed in this repository.
9. **Workflow gap.** The five new Python files are not in the workflow's
   literal Ruff path lists. Rule whether this should block M4.2 or become the
   next narrowly scoped workflow correction. Do not silently edit the workflow
   during this review.
10. **Out-of-tree import.** Reproduce the installed import from outside the
    checkout. The supported surface is `import bsm3.mesh_motion as mm`, not
    package-root `from bsm3 import PanelCondition`; do not mistake the latter
    for a promised export.

## Gates to reproduce

Use the validated Python 3.12 environment. Do not install or execute VortexAD,
DAFoam, OpenFOAM, or MPI.

```bash
python -m pytest -q tests/test_panel_aerodynamics.py tests/test_fuel_burn.py
python -m pytest -q tests -m "not integration"
python -m pytest -q tests/test_boundary_surface_movement.py
python -m pytest -q tests/test_e175_example.py -m "not integration"
python -m pytest -q tests/test_derivative_gate.py tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_e175_example.py -k "test_triangle_wall_at_full_deformation_scale or test_quad_panel_introduces_no_new_inverted_elements"
python -m pytest -q tests/test_documentation.py
python -m sphinx -W --keep-going -b html docs /tmp/gamma-turn75-docs-html
```

Expected numerical counts from Codex, to verify rather than assume:

- new tests: **12 passed, 1 skipped**;
- full non-integration: **240 passed, 10 deselected**;
- core: **45 passed**;
- fast E175: **16 passed, 5 deselected**;
- derivative/N-gon: **exactly 6 passed**;
- full-scale M4.1 guards: **2 passed, 19 deselected**;
- documentation: **12 passed**;
- strict Sphinx: success.

Run the five literal workflow Ruff commands unchanged, default Ruff on all
changed Python paths, and `ruff check --select D` on the five new Python files.
Reproduce a fresh-clone strict documentation build and an out-of-tree installed
import with VortexAD absent; require an empty clean-clone status.

## Ruling and handoff

If all claims hold, accept M4.2 and close M4. If a defect is found, issue one
narrow corrective prompt with a literal allowlist and preserve every accepted
M4.1/GAMMA behavior. Record the exact VortexAD pin, pass/skip counts, the Ruff
workflow-coverage ruling, clean-clone proof, and preservation hashes.

Do not rename the repository, create/push a tag, create a Read the Docs project,
publish to PyPI, start the blocked `bsm3` namespace migration, or begin M3.
Those remain separate user-authorized/external or later milestones.
