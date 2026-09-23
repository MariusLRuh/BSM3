# Review prompt for Claude — Turn 19 (M1.3 acceptance)

Read `docs/overhaul/PLAN.md` and `docs/overhaul/LOG.md` through Turn 18. Review
the M1.3 implementation at commit `1e3adfb` and the following documentation
close commit at `HEAD`.

## Review scope

Independently verify that Codex implemented the Turn-18 prompt without widening
the approved architecture:

1. Confirm complete removal of the membrane/corotational implementation,
   inversion penalty, OML log-barrier optimizer, tangential-smoothing API,
   parameterized-projection path, one-valued surface mode, and obsolete
   `_dafoam_mpi_refactor_backups/` directory.
2. Review the additional collapse of `use_corotational_reference=True` in
   `ElasticityMotionSolver`. Codex found that the required `corotational` grep
   also covered this one-valued graph-solver option. Verify that making the
   owner-reference formulation unconditional and deleting its unreachable
   absolute-formulation branch preserves the active behavior.
3. Confirm that ordinary `project_onto_oml`, `reevaluate_vertices`,
   `combine_vertices`, `VertexBatch`, `_project_group`, and
   `_coefficient_subset` remain; likewise preserve graph Laplacian motion,
   quadratic distortion, N-gon affine regularization, STEP-to-aerodynamic-mesh
   support, surface/volume quality diagnostics, and MPI barriers.
4. Audit `elasticity.py`, `motion.py`, `projection.py`, and `load_stepping.py`
   for stale imports, exports, fields, and orphaned private helpers.
5. Check that no excluded dirty or untracked user file entered either commit.

## Re-run acceptance

Use the live-code-scoped greps from the Turn-18 prompt. The barrier grep must
contain exactly seven MPI sites across the four documented files, while
`tangential_smoothing_step` in the independent SDF implementation must remain.
Run import/`__all__` smoke checks, focused M1.4 and derivative tests, and the
full suite in the `central_geom` environment. Ruff was unavailable locally;
perform an equivalent static review or run Ruff if your environment has it.

Codex recorded:

- focused suites: 41 + 8 + 10 + 29 passed;
- dirty working tree: 171 passed in 33.49 s, including excluded untracked tests;
- genuine no-hardlinks clone: 157 passed, 1 skipped in 32.25 s;
- implementation commit: `1e3adfb`.

## Deliverable

Append Turn 19 to `docs/overhaul/LOG.md` with findings and the exact commands
and counts you verified. If M1.3 is accepted, mark it **COMPLETE** in
`docs/overhaul/PLAN.md` and replace this file with the next bounded Codex prompt.
Per the established sequence, M1.1 and M1.2 open together next; do not start
their implementation during review. If you find a defect, leave M1.3 open and
write a literal corrective allowlist and acceptance criteria. Do not silently
edit production code unless the review finding itself requires a narrowly
scoped correction, and report any such edit prominently.
