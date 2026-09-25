# Claude Turn 77 — review M7.1 CI lint coverage

Codex implemented the narrow M7.1 workflow correction in `b5e14f6`. Review
independently and do not self-expand this into publication, namespace migration,
or release pruning.

## Scope

Base: `fb833d5` (the prompt itself is `d6c2b87`)

Implementation commit: `b5e14f6`

The implementation commit must change exactly one path:

```text
.github/workflows/actions.yml
```

The handoff commit may change only:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Expected preservation:

```text
8 modified tracked files
393 untracked entries
dirty diff:     981318561a10dff8e9d723540902b6d2560875b29656a0b59f0803cbff116177
untracked list: c38fd93dc32ecf7f927fc612c1079bd9786c19f6c1f74b4f8e69d28aaa44da60
```

## Review questions

1. Confirm `fuel_burn.py` and `panel_aerodynamics.py` occur exactly once in
   **Critical static checks** and exactly once in **Numpydoc checks for the
   surface-motion core**, and nowhere else in the workflow.
2. Confirm their placement retains the local ordering and backslash style and
   that no existing path, command, comment, step name, or dependency changed.
3. Review the Part-B ruling rather than accepting it automatically: the two new
   tests and tracked optimization example were not added. Codex's principle is
   that these lists cover the retained production manifest plus designated M0
   tests, not all repository Python. The full test job executes the test files,
   and a structural test parses the example. Decide whether that is consistent
   with the established workflow policy. If not, issue a new narrow prompt;
   do not fold a broader policy change into this review.
4. Confirm the workflow parses as valid YAML and has the same 11 ordered step
   names as `fb833d5`.
5. Confirm the Turn-75 VortexAD mutable-default hazard is recorded accurately
   in `LOG.md` and was not worked around in production code.

## Executable verification

Parse the base and edited YAML, extract the five Ruff `run` blocks by step
name, and execute the edited blocks literally rather than reconstructing them
manually. Expected path counts and results:

| Ruff step | Before | After | Expected |
| --- | ---: | ---: | --- |
| Critical static checks | 53 | 55 | pass |
| M0 public surface | 4 | 4 | pass |
| Surface-motion core | 18 | 20 | pass |
| Projection and preprocessing | 15 | 15 | pass |
| Drivers, volume motion, and MPI | 17 | 17 | pass |

Then run:

```bash
python -m pytest -q tests -m "not integration"
python -m pytest -q tests/test_documentation.py
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 python -m sphinx -W --keep-going -b html docs /tmp/gamma-turn77-docs-html
```

Expected results are **240 passed / 10 deselected**, **12 passed**, and a
warning-free strict Sphinx 9.1.0 build. Also require
`git diff --check fb833d5..HEAD`, the exact changed-path allowlists, and both
preservation hashes.

## Ruling

If the implementation and Part-B policy hold, accept M7.1 and close M7. If
not, write one concrete corrective prompt with a literal allowlist. Do not
rename or publish the GitHub repository, create the Read the Docs project or
webhook, create/push a tag, publish to PyPI, start M5.2, or begin M3.
