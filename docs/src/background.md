# Background

This page explains what each pipeline stage does and why the settings exist.

## The problem

When a CAD outer mould line deforms, a surface mesh attached to it must follow.
Moving only the boundary nodes and leaving the interior alone tangles the mesh;
moving everything rigidly ignores the shape change. BSM3 propagates the motion
through the mesh graph, then puts every node back exactly on the deformed
geometry, and keeps the whole map differentiable so it can sit inside an
optimization.

## Stages

### Intersections

Components meet along closed curves — a wing root against a fuselage, a tail
root against the same body. `connect` names such a curve. Those curves are
recomputed for the deformed geometry, because where the wing meets the body
moves when the wing does.

### Surface motion

The interior is propagated with a **graph Laplacian** over the mesh edges.
Several settings shape that solve:

- **`load_steps`** applies the motion in increments rather than all at once.
  More steps cost more but survive larger deformations.
- **`stiffening_exponent`** makes small cells stiffer than large ones, so fine
  regions distort less than coarse ones.
- **`distance_weighting`** adds a setup-time secondary edge weight based on
  geodesic distance from the moving seams, which controls the *blending length*
  of the transition. `beta = 0` reproduces plain inverse-area weighting exactly.
  The distance field and its multipliers are reference constants: they never
  depend on the current displacement, so they carry no derivative.
- **`polygon_regularization`** constrains the affine *hourglass* modes that a
  quad or higher-order polygon admits. A triangle has none, so on a
  triangle-only mesh a positive weight is simply inactive. This is why the same
  settings work for both the triangle wall and the quad-dominant panel.
- **`distortion_penalty`** optionally penalizes element distortion directly.

### Reprojection

Every moved node is projected back onto the deformed outer mould line, so the
mesh describes the actual geometry rather than an approximation of it. This
uses a warm-started Newton solve with candidate ranking across patches and
patch boundaries.

### Quality diagnostics

Three inversion reports are produced with the same metric — on the untouched
input mesh, after motion but before reprojection, and on the final surface — so
any two can be compared directly. That separation matters: an element inverted
in the *input* mesh is not a defect the solve introduced.

A **fold** is a polygon whose area-weighted (Newell) normal flipped direction
between the undeformed and deformed mesh. It is measured on the original
polygonal cells rather than on fan triangles, because fan-triangulating an
n-gon invents sliver cells that report spurious inversions.

### Volume motion (optional)

Separate from surface motion. Two propagators are available for the volume:
graph-based and linear elasticity. They move a tetrahedral or hybrid volume
mesh to follow the deformed wall.

## Differentiability

The pipeline is built as a CSDL graph, so derivatives of the final reprojected
coordinates with respect to your design variables are analytic rather than
finite-differenced. Reference-constant quantities — the distance field, the
factorized operators used as reference matrices — deliberately carry no
derivative, which keeps the reverse pass exact and cheap.

Points whose reprojection Newton solve did not converge are still returned
rather than raising. The convergence evidence lives in the diagnostics;
derivative quality at non-converged points is not guaranteed.

## Caching

Setup work — baseline projection ownership, seam identification, elasticity
assembly and factorization — is expensive and depends only on the reference
geometry and mesh. It is cached in `cache_directory` and reused. The cache key
covers the code that produced it, so changing that logic invalidates the cache
rather than silently reusing a stale result.
