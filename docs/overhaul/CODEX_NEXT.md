# Claude Turn 70 — Plan GAMMA identity and the first Read the Docs alpha

M4.1 is accepted. Do **not** begin M4.2 yet. The user has promoted the GAMMA
identity decision and an initial versioned Read the Docs release ahead of the
VortexAD/fuel-burn implementation.

Turn 68's complete M4.2 prompt is preserved verbatim at:

```bash
git show 38cd0bf:docs/overhaul/CODEX_NEXT.md
```

Do not rewrite or weaken that prompt. Queue it after the identity and docs
publication milestones.

## Scope of this turn

This is a **planning and ruling turn only**. Inspect the repository and external
name availability, update `PLAN.md` and `LOG.md`, and replace this file with one
literal Codex implementation prompt. Do not rename files, imports, the GitHub
repository, or the Read the Docs project. Do not create a tag, reserve a name,
push, publish, install dependencies, or alter user-owned dirty files.

## Proposed public identity

```text
Display name:        GAMMA
Expansion:           Geometry Adaptation for Multidisciplinary Modeling and Analysis
Repository slug:     GAMMA-MDO
Python distribution: gamma-mdo
Python import:       gamma_mdo
Read the Docs slug:  gamma-mdo
Candidate first tag: v0.1.0a1
```

The display name and expansion are the leading proposal, not permission to
assume every technical identifier. Bare `gamma` is already occupied on PyPI
and is overloaded in this domain. Verify availability of every proposed
qualified identifier from authoritative sources and distinguish "not found"
from "reserved successfully"; this turn authorizes no reservation.

## Required rulings

### 1. Rename boundary

Rule separately on:

- human-facing project/docs name;
- GitHub repository slug;
- Python distribution name in packaging metadata;
- Python import namespace and tracked `bsm3/` directory;
- Read the Docs project slug.

The key question is whether the first alpha should already use
`import gamma_mdo`, or whether GAMMA should deliberately retain `import bsm3`
as a stable implementation namespace (as distributions such as scikit-learn
use a different import name). Do not hide this choice inside mechanical rename
work. Recommend one, enumerate migration consequences, and make the eventual
Codex prompt reflect the ruling. The user previously accepted a clean break;
do not add a compatibility shim unless you establish a concrete need and ask
for approval.

### 2. Version policy

The source currently says `0.1.4`, setup metadata derives from it, and the local
repository has no tags. Determine whether `0.1.4` has ever been publicly
released or published. Use `v0.1.0a1` only if moving to it does not create a
public version regression; otherwise choose a forward-moving PEP 440
prerelease. Keep source, built metadata, Sphinx `version`/`release`, Git tag,
and RTD version label coherent.

### 3. Dirty-tree-safe implementation

The live checkout contains eight modified tracked files and 393 untracked
entries, many under `bsm3/`. A wholesale directory move could relocate, stage,
or lose user-owned work. Design a concrete safe workflow, preferably an
isolated worktree/branch from the accepted committed state, and explain how the
result can be integrated without overwriting the live dirty files. If a full
import-package rename cannot be safely integrated until the dirty work is
resolved, say so and separate public branding from namespace migration rather
than pretending the risk does not exist.

### 4. Read the Docs alpha boundary

The repository already has a hermetic Sphinx site and a v2
`.readthedocs.yaml`. Plan the first release as HTML-only because only HTML has
been verified; PDF/HTMLZIP can follow after independent builds. Specify the
project import, webhook, tag activation/default-version policy, badge/link
update, and clean-build proof. Distinguish repository changes Codex can prepare
from external actions requiring explicit user authorization.

No CSDL_alpha, LFS, JAX, gmsh, DAFoam, MPI, VortexAD, or geometry assets should
be needed merely to build the hosted documentation.

## Implementation-prompt requirements

The next literal Codex prompt must:

- have a per-path allowlist and explicit prohibited paths;
- preserve historical `docs/overhaul` prose rather than mechanically replacing
  every occurrence of BSM3;
- define exact greps for stale supported-surface names without demanding that
  historical collaboration text be rewritten;
- keep the eight modified and 393 untracked entries safe;
- require package-build/install/import checks from outside the source tree;
- require the full non-integration suite, E175 integration guards,
  derivative/N-gon guard, all five Ruff groups, documentation tests, and strict
  Sphinx;
- test the old import's intended clean-break behavior if the namespace changes;
- keep external mutations (GitHub rename, RTD project creation, tag/push, PyPI
  publication or reservation) in a separately enumerated user-authorized step;
  and
- leave M4.2 queued, recoverable from `38cd0bf`, with M3 archive/history
  pruning separate and last.

If any identifier or version-history fact cannot be established, issue a
short, evidence-backed decision question instead of inventing it.

## Handoff

Commit only `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md`. Report the identifier and
version rulings, external availability evidence, dirty-tree strategy, exact
next milestone ordering, and the commit hash. Do not mark a rename or hosted
release complete; neither has started.
