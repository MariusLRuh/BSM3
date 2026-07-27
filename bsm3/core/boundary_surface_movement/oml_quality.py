"""Fixed-domain, CAD-constrained surface-mesh quality optimization.

The graph/membrane propagators are predictors.  This module performs the final
quality correction in CAD parameter space, so every corrected point remains on
its selected deformed B-spline patch.  The mathematical vertex domain is fixed
at setup time; no quality-triggered repair patch is created during a design
evaluation.

The forward solve has two phases:

1. a squared corner-orientation penalty restores feasibility when the projected
   predictor is inverted;
2. a smooth IPC-style log barrier and a graph-relative distortion energy
   improve the feasible result.

The custom VJP applies the implicit-function theorem to the converged second
phase.  It uses JAX Hessian-vector products and a matrix-free reduced tangent
solve, rather than differentiating through L-BFGS iterations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import csdl_alpha as csdl
import jax

# Surface quality is sensitive to roundoff near zero orientation.  Enable x64
# before constructing the JAX functions used by this module.
jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp
import numpy as np
from scipy.optimize import minimize
from scipy.sparse.linalg import LinearOperator, cg, minres

from lsdo_function_spaces.core.spaces.non_cython_bsplines.compute_basis_matrix_jax_stencil import (
    evaluate_b_spline_jax_fast,
)

from bsm3.preprocessing.mesh_io import _as_mesh_data

from .projection import ParameterizedProjectionGroup


@dataclass(frozen=True)
class OMLQualitySolveInfo:
    quality_vertices: int
    support_cells: int
    feasibility_iterations: int
    quality_iterations: int
    minimum_oriented_ratio: float
    final_gradient_inf_norm: float
    active_bound_dofs: int
    quality_solver_success: bool


@dataclass(frozen=True)
class _GroupSpec:
    vertex_ids: np.ndarray
    selected_input_rows: np.ndarray
    quality_rows: np.ndarray
    fixed_parametric_coordinates: np.ndarray | None
    evaluation_model: object


@dataclass(frozen=True)
class _PatchRecord:
    group_index: int
    patch_id: int
    quality_rows: np.ndarray
    global_vertex_ids: np.ndarray
    coefficient_start: int
    coefficient_stop: int
    coefficient_shape: tuple[int, ...]
    degrees: tuple[int, ...]
    knot_vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class _Branch:
    initial_uv: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    records: tuple[_PatchRecord, ...]


@dataclass(frozen=True)
class _SolveState:
    optimized_uv: np.ndarray
    branch: _Branch
    candidate_vertices: np.ndarray
    coefficients: tuple[np.ndarray, ...]
    info: OMLQualitySolveInfo


def select_fixed_vertex_band(
    mesh,
    *,
    seed_ids: np.ndarray,
    allowed_ids: np.ndarray,
    excluded_ids: np.ndarray = np.empty(0, dtype=np.int64),
    element_layers: int = 4,
) -> np.ndarray:
    """Return a topology-fixed element-layer band around ``seed_ids``."""

    if int(element_layers) < 1:
        raise ValueError("element_layers must be at least one.")
    mesh_data = _as_mesh_data(mesh)
    cells = []
    for block in mesh_data.cell_blocks.values():
        array = np.asarray(block, dtype=np.int64)
        if array.ndim == 2 and array.shape[1] >= 3:
            cells.extend(np.asarray(cell, dtype=np.int64) for cell in array)

    patch = set(int(item) for item in np.asarray(seed_ids, dtype=np.int64).reshape(-1))
    for _ in range(int(element_layers)):
        touching = [
            cell for cell in cells if any(int(vertex) in patch for vertex in cell)
        ]
        patch.update(int(vertex) for cell in touching for vertex in cell)

    allowed = set(
        int(item) for item in np.asarray(allowed_ids, dtype=np.int64).reshape(-1)
    )
    excluded = set(
        int(item) for item in np.asarray(excluded_ids, dtype=np.int64).reshape(-1)
    )
    return np.asarray(sorted((patch & allowed) - excluded), dtype=np.int64)


class OMLQualityModel:
    """Topology, CAD branches, objective, and nonlinear quality solve."""

    def __init__(
        self,
        mesh,
        *,
        quality_vertex_ids: np.ndarray,
        parameter_groups: Sequence[ParameterizedProjectionGroup],
        proximity_weight: float = 1.0,
        edge_distortion_weight: float = 0.25,
        feasibility_target: float = 0.12,
        barrier_floor: float = 0.01,
        barrier_activation: float = 0.20,
        barrier_weight: float = 10.0,
        max_feasibility_iterations: int = 250,
        max_quality_iterations: int = 250,
        quality_solver: str = "lbfgs",
        adjoint_stationarity_tolerance: float = 1e-4,
        tolerance: float = 1e-10,
        verbose: bool = False,
    ):
        if not (0.0 < float(barrier_floor) < float(feasibility_target)):
            raise ValueError("Require 0 < barrier_floor < feasibility_target.")
        if not (
            float(feasibility_target) < float(barrier_activation) < 1.0
        ):
            raise ValueError(
                "Require feasibility_target < barrier_activation < 1."
            )
        if float(proximity_weight) <= 0.0:
            raise ValueError("proximity_weight must be positive.")
        if float(edge_distortion_weight) < 0.0:
            raise ValueError("edge_distortion_weight must be non-negative.")
        if float(barrier_weight) <= 0.0:
            raise ValueError("barrier_weight must be positive.")
        if float(adjoint_stationarity_tolerance) <= 0.0:
            raise ValueError("adjoint_stationarity_tolerance must be positive.")
        quality_solver = str(quality_solver).strip().lower()
        if quality_solver not in ("lbfgs", "trust-krylov"):
            raise ValueError(
                "quality_solver must be 'lbfgs' or 'trust-krylov'."
            )

        mesh_data = _as_mesh_data(mesh)
        self.baseline = np.asarray(mesh_data.vertices, dtype=float).reshape((-1, 3))
        self.quality_vertex_ids = np.unique(
            np.asarray(quality_vertex_ids, dtype=np.int64).reshape(-1)
        )
        if self.quality_vertex_ids.size == 0:
            raise ValueError("quality_vertex_ids must not be empty.")
        if np.any(
            (self.quality_vertex_ids < 0)
            | (self.quality_vertex_ids >= self.baseline.shape[0])
        ):
            raise ValueError("quality_vertex_ids contains an invalid mesh row.")
        self._quality_local = {
            int(vertex): row
            for row, vertex in enumerate(self.quality_vertex_ids)
        }
        quality_set = set(self._quality_local)

        group_specs = []
        coverage = np.zeros(self.quality_vertex_ids.size, dtype=np.int64)
        for group in parameter_groups:
            vertex_ids = np.asarray(group.vertex_ids, dtype=np.int64).reshape(-1)
            selected = np.asarray(
                [
                    row
                    for row, vertex in enumerate(vertex_ids)
                    if int(vertex) in quality_set
                ],
                dtype=np.int64,
            )
            if selected.size == 0:
                continue
            quality_rows = np.asarray(
                [self._quality_local[int(vertex_ids[row])] for row in selected],
                dtype=np.int64,
            )
            coverage[quality_rows] += 1
            fixed = group.fixed_parametric_coordinates
            if fixed is not None:
                fixed = np.asarray(fixed, dtype=float).reshape((-1, 2))[selected]
            group_specs.append(
                _GroupSpec(
                    vertex_ids=vertex_ids,
                    selected_input_rows=selected,
                    quality_rows=quality_rows,
                    fixed_parametric_coordinates=fixed,
                    evaluation_model=group.evaluation_model,
                )
            )
        if np.any(coverage != 1):
            bad = self.quality_vertex_ids[coverage != 1]
            raise ValueError(
                "Each quality vertex must occur in exactly one parameter group; "
                f"bad rows: {bad[:10].tolist()}."
            )
        self.group_specs = tuple(group_specs)

        all_cells: list[np.ndarray] = []
        support_cells: list[np.ndarray] = []
        for block in mesh_data.cell_blocks.values():
            array = np.asarray(block, dtype=np.int64)
            if array.ndim != 2 or array.shape[1] < 3:
                continue
            for cell in array:
                item = np.asarray(cell, dtype=np.int64)
                all_cells.append(item)
                if any(int(vertex) in quality_set for vertex in item):
                    support_cells.append(item)
        if not support_cells:
            raise ValueError("No surface cells touch the OML quality domain.")
        self.support_cells = tuple(support_cells)

        (
            self.corner_previous,
            self.corner_center,
            self.corner_following,
            self.corner_normals,
            self.corner_inverse_reference,
        ) = self._corner_data(self.support_cells)
        (
            self.all_corner_previous,
            self.all_corner_center,
            self.all_corner_following,
            self.all_corner_normals,
            self.all_corner_inverse_reference,
        ) = self._corner_data(all_cells)

        edges = set()
        for cell in support_cells:
            for index, vertex in enumerate(cell):
                following = int(cell[(index + 1) % cell.size])
                a, b = sorted((int(vertex), following))
                edges.add((a, b))
        ordered_edges = np.asarray(sorted(edges), dtype=np.int64)
        self.edge_a = ordered_edges[:, 0]
        self.edge_b = ordered_edges[:, 1]
        edge_lengths = np.linalg.norm(
            self.baseline[self.edge_a] - self.baseline[self.edge_b],
            axis=1,
        )
        self.length_scale = max(float(np.median(edge_lengths)), 1e-12)

        self.proximity_weight = float(proximity_weight)
        self.edge_distortion_weight = float(edge_distortion_weight)
        self.feasibility_target = float(feasibility_target)
        self.barrier_floor = float(barrier_floor)
        self.barrier_activation = float(barrier_activation)
        self.barrier_weight = float(barrier_weight)
        self.max_feasibility_iterations = int(max_feasibility_iterations)
        self.max_quality_iterations = int(max_quality_iterations)
        self.quality_solver = quality_solver
        self.adjoint_stationarity_tolerance = float(
            adjoint_stationarity_tolerance
        )
        self.tolerance = float(tolerance)
        self.verbose = bool(verbose)

    def _corner_data(self, cells):
        previous = []
        center = []
        following = []
        normals = []
        inverse_reference = []
        for cell in cells:
            polygon = self.baseline[cell]
            normal = np.sum(
                np.cross(polygon, np.roll(polygon, -1, axis=0)),
                axis=0,
            )
            magnitude = float(np.linalg.norm(normal))
            if magnitude <= 1e-14:
                raise ValueError("Quality support contains a degenerate polygon.")
            normal /= magnitude
            for index, vertex in enumerate(cell):
                p = int(cell[index - 1])
                q = int(vertex)
                r = int(cell[(index + 1) % cell.size])
                reference = float(
                    np.dot(
                        np.cross(
                            self.baseline[q] - self.baseline[p],
                            self.baseline[r] - self.baseline[p],
                        ),
                        normal,
                    )
                )
                if reference <= 0.0:
                    raise ValueError(
                        "Baseline polygon has a non-positive corner orientation."
                    )
                previous.append(p)
                center.append(q)
                following.append(r)
                normals.append(normal)
                inverse_reference.append(1.0 / reference)
        return (
            np.asarray(previous, dtype=np.int64),
            np.asarray(center, dtype=np.int64),
            np.asarray(following, dtype=np.int64),
            np.asarray(normals, dtype=float),
            np.asarray(inverse_reference, dtype=float),
        )

    def _build_branch(
        self,
        parametric_coordinates: Sequence[np.ndarray],
    ) -> _Branch:
        if len(parametric_coordinates) != len(self.group_specs):
            raise ValueError("Parametric input count does not match quality groups.")
        count = self.quality_vertex_ids.size
        initial_uv = np.zeros((count, 2), dtype=float)
        lower = np.full((count, 2), 1e-10, dtype=float)
        upper = np.full((count, 2), 1.0 - 1e-10, dtype=float)
        records: list[_PatchRecord] = []

        for group_index, (spec, coordinates) in enumerate(
            zip(self.group_specs, parametric_coordinates)
        ):
            coordinates = np.asarray(coordinates, dtype=float).reshape((-1, 3))
            selected = coordinates[spec.selected_input_rows]
            initial_uv[spec.quality_rows] = np.clip(
                selected[:, 1:3],
                0.0,
                1.0,
            )
            if spec.fixed_parametric_coordinates is not None:
                for axis in (0, 1):
                    fixed_rows = np.where(
                        np.isfinite(spec.fixed_parametric_coordinates[:, axis])
                    )[0]
                    if fixed_rows.size:
                        quality_rows = spec.quality_rows[fixed_rows]
                        values = spec.fixed_parametric_coordinates[fixed_rows, axis]
                        initial_uv[quality_rows, axis] = values
                        lower[quality_rows, axis] = values
                        upper[quality_rows, axis] = values

            patch_ids = np.rint(selected[:, 0]).astype(np.int64)
            invalid = sorted(
                set(patch_ids.tolist())
                - set(int(item) for item in spec.evaluation_model.patch_ids)
            )
            if invalid:
                raise ValueError(
                    f"Projected patch ids {invalid} are outside their CAD group."
                )
            for patch_id in np.unique(patch_ids):
                local = np.where(patch_ids == int(patch_id))[0]
                info = spec.evaluation_model.patch_infos[int(patch_id)]
                records.append(
                    _PatchRecord(
                        group_index=group_index,
                        patch_id=int(patch_id),
                        quality_rows=spec.quality_rows[local],
                        global_vertex_ids=self.quality_vertex_ids[
                            spec.quality_rows[local]
                        ],
                        coefficient_start=int(info.start),
                        coefficient_stop=int(info.stop),
                        coefficient_shape=tuple(info.coefficient_shape),
                        degrees=tuple(int(item) for item in info.degrees),
                        knot_vectors=tuple(
                            tuple(float(value) for value in knot)
                            for knot in info.knot_vectors
                        ),
                    )
                )
        return _Branch(
            initial_uv=initial_uv.reshape(-1),
            lower_bounds=lower.reshape(-1),
            upper_bounds=upper.reshape(-1),
            records=tuple(records),
        )

    def _make_functions(self, branch: _Branch):
        quality_ids = jnp.asarray(self.quality_vertex_ids)
        edge_a = jnp.asarray(self.edge_a)
        edge_b = jnp.asarray(self.edge_b)
        previous = jnp.asarray(self.corner_previous)
        center = jnp.asarray(self.corner_center)
        following = jnp.asarray(self.corner_following)
        normals = jnp.asarray(self.corner_normals)
        inverse_reference = jnp.asarray(self.corner_inverse_reference)
        lower_bounds = jnp.asarray(branch.lower_bounds)
        upper_bounds = jnp.asarray(branch.upper_bounds)
        length_scale = self.length_scale

        def positions(uv_flat, coefficients, candidate_vertices):
            points = jnp.asarray(candidate_vertices)
            uv = uv_flat.reshape((-1, 2))
            for record in branch.records:
                coeff = coefficients[record.group_index][
                    record.coefficient_start : record.coefficient_stop
                ].reshape(record.coefficient_shape)
                values = evaluate_b_spline_jax_fast(
                    uv[jnp.asarray(record.quality_rows)],
                    record.degrees,
                    record.knot_vectors,
                    coeff,
                )
                points = points.at[
                    jnp.asarray(record.global_vertex_ids)
                ].set(values)
            return points

        def ratios(points):
            edge_q = points[center] - points[previous]
            edge_r = points[following] - points[previous]
            return (
                jnp.sum(jnp.cross(edge_q, edge_r) * normals, axis=1)
                * inverse_reference
            )

        def regularization(points, candidate_vertices):
            difference = (
                points[quality_ids] - candidate_vertices[quality_ids]
            ) / length_scale
            value = 0.5 * self.proximity_weight * jnp.sum(
                difference * difference
            )
            if self.edge_distortion_weight:
                current_edge = points[edge_b] - points[edge_a]
                candidate_edge = (
                    candidate_vertices[edge_b] - candidate_vertices[edge_a]
                )
                edge_difference = (current_edge - candidate_edge) / length_scale
                value = value + 0.5 * self.edge_distortion_weight * jnp.sum(
                    edge_difference * edge_difference
                )
            return value

        def feasibility_objective(
            uv_flat,
            coefficients,
            candidate_vertices,
            penalty_weight,
        ):
            points = positions(uv_flat, coefficients, candidate_vertices)
            corner_ratio = ratios(points)
            deficit = jnp.minimum(
                corner_ratio - self.feasibility_target,
                0.0,
            )
            return regularization(points, candidate_vertices) + (
                0.5 * penalty_weight * jnp.sum(deficit * deficit)
            )

        def quality_objective(uv_flat, coefficients, candidate_vertices):
            points = positions(uv_flat, coefficients, candidate_vertices)
            corner_ratio = ratios(points)
            scale = self.barrier_activation - self.barrier_floor
            normalized = (
                corner_ratio - self.barrier_floor
            ) / scale
            safe = jnp.maximum(normalized, 1e-12)
            barrier = jnp.where(
                corner_ratio < self.barrier_activation,
                -(1.0 - normalized) ** 2 * jnp.log(safe),
                0.0,
            )
            # A finite guard lets line-search trial points be evaluated while
            # making an infeasible accepted point overwhelmingly unfavorable.
            violation = jnp.minimum(normalized, 0.0)
            guard = 1e6 * jnp.sum(violation * violation)
            lower_violation = jnp.minimum(uv_flat - lower_bounds, 0.0)
            upper_violation = jnp.maximum(uv_flat - upper_bounds, 0.0)
            bound_guard = 1e8 * (
                jnp.sum(lower_violation * lower_violation)
                + jnp.sum(upper_violation * upper_violation)
            )
            return (
                regularization(points, candidate_vertices)
                + self.barrier_weight * jnp.sum(barrier)
                + guard
                + bound_guard
            )

        return positions, ratios, feasibility_objective, quality_objective

    def _numpy_corner_ratios(self, points, *, all_cells=False):
        if all_cells:
            p = self.all_corner_previous
            q = self.all_corner_center
            r = self.all_corner_following
            normals = self.all_corner_normals
            inverse = self.all_corner_inverse_reference
        else:
            p = self.corner_previous
            q = self.corner_center
            r = self.corner_following
            normals = self.corner_normals
            inverse = self.corner_inverse_reference
        edge_q = points[q] - points[p]
        edge_r = points[r] - points[p]
        return (
            np.einsum("ij,ij->i", np.cross(edge_q, edge_r), normals)
            * inverse
        )

    def solve(
        self,
        candidate_vertices: np.ndarray,
        parametric_coordinates: Sequence[np.ndarray],
        coefficients: Sequence[np.ndarray],
        *,
        return_state: bool = False,
    ):
        candidate = np.asarray(candidate_vertices, dtype=float).reshape((-1, 3))
        if candidate.shape != self.baseline.shape:
            raise ValueError("candidate_vertices must contain the complete mesh.")
        coefficient_values = tuple(
            np.asarray(item, dtype=float) for item in coefficients
        )
        branch = self._build_branch(parametric_coordinates)
        (
            positions,
            _,
            feasibility_objective,
            quality_objective,
        ) = self._make_functions(branch)
        coefficient_jax = tuple(jnp.asarray(item) for item in coefficient_values)
        candidate_jax = jnp.asarray(candidate)
        bounds = list(
            zip(branch.lower_bounds.tolist(), branch.upper_bounds.tolist())
        )
        uv = branch.initial_uv.copy()
        feasibility_iterations = 0

        feasibility_value_gradient = jax.jit(
            jax.value_and_grad(feasibility_objective, argnums=0)
        )

        def run_feasibility(weight):
            def objective(values):
                value, gradient = feasibility_value_gradient(
                    jnp.asarray(values),
                    coefficient_jax,
                    candidate_jax,
                    float(weight),
                )
                return float(value), np.asarray(gradient, dtype=float)

            return minimize(
                objective,
                uv,
                method="L-BFGS-B",
                jac=True,
                bounds=bounds,
                options={
                    "maxiter": self.max_feasibility_iterations,
                    "ftol": self.tolerance,
                    "gtol": 1e-8,
                    "maxls": 50,
                },
            )

        initial_points = np.asarray(
            positions(
                jnp.asarray(uv),
                coefficient_jax,
                candidate_jax,
            ),
            dtype=float,
        )
        minimum = float(np.min(self._numpy_corner_ratios(initial_points)))
        if minimum <= self.barrier_floor:
            for weight in (500.0, 5_000.0, 50_000.0):
                result = run_feasibility(weight)
                uv = np.asarray(result.x, dtype=float)
                feasibility_iterations += int(result.nit)
                trial_points = np.asarray(
                    positions(
                        jnp.asarray(uv),
                        coefficient_jax,
                        candidate_jax,
                    ),
                    dtype=float,
                )
                minimum = float(
                    np.min(self._numpy_corner_ratios(trial_points))
                )
                if minimum > self.barrier_floor + 1e-5:
                    break
        if minimum <= self.barrier_floor:
            raise RuntimeError(
                "OML feasibility restoration failed; minimum normalized corner "
                f"orientation is {minimum:+.3e}."
            )

        quality_value_gradient = jax.jit(
            jax.value_and_grad(quality_objective, argnums=0)
        )

        def quality_fun(values):
            value, gradient = quality_value_gradient(
                jnp.asarray(values),
                coefficient_jax,
                candidate_jax,
            )
            return float(value), np.asarray(gradient, dtype=float)

        if self.quality_solver == "trust-krylov":
            quality_gradient = jax.grad(quality_objective, argnums=0)
            quality_hvp = jax.jit(
                lambda values, vector: jax.jvp(
                    lambda current: quality_gradient(
                        current,
                        coefficient_jax,
                        candidate_jax,
                    ),
                    (values,),
                    (vector,),
                )[1]
            )

            def trust_value(values):
                return quality_fun(values)[0]

            def trust_gradient(values):
                return quality_fun(values)[1]

            def trust_hessian_product(values, vector):
                return np.asarray(
                    quality_hvp(
                        jnp.asarray(values),
                        jnp.asarray(vector),
                    ),
                    dtype=float,
                )

            quality_result = minimize(
                trust_value,
                uv,
                method="trust-krylov",
                jac=trust_gradient,
                hessp=trust_hessian_product,
                options={
                    "maxiter": self.max_quality_iterations,
                    "gtol": 1e-6,
                    "initial_trust_radius": 0.1,
                    "max_trust_radius": 10.0,
                },
            )
        else:
            quality_result = minimize(
                quality_fun,
                uv,
                method="L-BFGS-B",
                jac=True,
                bounds=bounds,
                options={
                    "maxiter": self.max_quality_iterations,
                    "ftol": self.tolerance,
                    "gtol": 1e-8,
                    "maxls": 50,
                },
            )
        optimized_uv = np.asarray(quality_result.x, dtype=float)
        bound_violation = max(
            float(np.max(branch.lower_bounds - optimized_uv)),
            float(np.max(optimized_uv - branch.upper_bounds)),
        )
        if bound_violation > 1e-7:
            raise RuntimeError(
                "OML quality solve left its fixed CAD parameter bounds by "
                f"{bound_violation:.3e}."
            )
        final_points = np.asarray(
            positions(
                jnp.asarray(optimized_uv),
                coefficient_jax,
                candidate_jax,
            ),
            dtype=float,
        )
        all_ratios = self._numpy_corner_ratios(final_points, all_cells=True)
        final_minimum = float(np.min(all_ratios))
        if final_minimum <= 0.0:
            raise RuntimeError(
                "Fixed OML quality domain did not produce a globally "
                "orientation-positive mesh; minimum normalized corner "
                f"orientation is {final_minimum:+.3e}. Enlarge the fixed band."
            )
        _, final_gradient = quality_fun(optimized_uv)
        lower = branch.lower_bounds
        upper = branch.upper_bounds
        at_lower = optimized_uv <= lower + 1e-7
        at_upper = optimized_uv >= upper - 1e-7
        fixed = np.abs(upper - lower) <= 1e-14
        projected_gradient = np.asarray(final_gradient, dtype=float).copy()
        projected_gradient[at_lower & (projected_gradient > 0.0)] = 0.0
        projected_gradient[at_upper & (projected_gradient < 0.0)] = 0.0
        projected_gradient[fixed] = 0.0
        gradient_inf = float(np.max(np.abs(projected_gradient)))
        active_bound_dofs = int(np.count_nonzero(at_lower | at_upper | fixed))
        info = OMLQualitySolveInfo(
            quality_vertices=int(self.quality_vertex_ids.size),
            support_cells=len(self.support_cells),
            feasibility_iterations=feasibility_iterations,
            quality_iterations=int(quality_result.nit),
            minimum_oriented_ratio=final_minimum,
            final_gradient_inf_norm=gradient_inf,
            active_bound_dofs=active_bound_dofs,
            quality_solver_success=bool(quality_result.success),
        )
        state = _SolveState(
            optimized_uv=optimized_uv,
            branch=branch,
            candidate_vertices=candidate.copy(),
            coefficients=coefficient_values,
            info=info,
        )
        output = final_points[self.quality_vertex_ids]
        return (output, state, info) if return_state else output

    def compute_vjp(
        self,
        candidate_vertices,
        parametric_coordinates,
        coefficients,
        d_quality_vertices,
    ):
        _, state, _ = self.solve(
            candidate_vertices,
            parametric_coordinates,
            coefficients,
            return_state=True,
        )
        if (
            not state.info.quality_solver_success
            and state.info.final_gradient_inf_norm
            > self.adjoint_stationarity_tolerance
        ):
            raise RuntimeError(
                "OML quality adjoint requested before the fixed-domain "
                "equilibrium converged: projected gradient infinity norm is "
                f"{state.info.final_gradient_inf_norm:.3e}, tolerance is "
                f"{self.adjoint_stationarity_tolerance:.3e}."
            )
        positions, _, _, quality_objective = self._make_functions(state.branch)
        z = jnp.asarray(state.optimized_uv)
        coeff = tuple(jnp.asarray(item) for item in state.coefficients)
        candidate = jnp.asarray(state.candidate_vertices)
        cotangent = jnp.asarray(d_quality_vertices)
        quality_ids = jnp.asarray(self.quality_vertex_ids)

        def output_function(current_z, current_coeff, current_candidate):
            return positions(
                current_z,
                current_coeff,
                current_candidate,
            )[quality_ids]

        _, output_pullback = jax.vjp(
            output_function,
            z,
            coeff,
            candidate,
        )
        d_z, direct_coeff, direct_candidate = output_pullback(cotangent)

        gradient_function = jax.grad(quality_objective, argnums=0)
        lower = state.branch.lower_bounds
        upper = state.branch.upper_bounds
        z_numpy = np.asarray(z, dtype=float)
        active = (
            (z_numpy <= lower + 1e-7)
            | (z_numpy >= upper - 1e-7)
            | (np.abs(upper - lower) <= 1e-14)
        )
        free = np.where(~active)[0].astype(np.int64)
        lambda_full = np.zeros_like(z_numpy)
        if free.size:
            rhs = np.asarray(d_z, dtype=float)[free]

            def reduced_hvp(vector):
                full = jnp.zeros_like(z).at[jnp.asarray(free)].set(
                    jnp.asarray(vector)
                )
                hvp = jax.jvp(
                    lambda current_z: gradient_function(
                        current_z,
                        coeff,
                        candidate,
                    ),
                    (z,),
                    (full,),
                )[1]
                reduced = np.asarray(hvp, dtype=float)[free]
                return reduced + 1e-8 * np.asarray(vector, dtype=float)

            if free.size <= 64:
                hessian = np.asarray(
                    jax.hessian(quality_objective, argnums=0)(
                        z,
                        coeff,
                        candidate,
                    ),
                    dtype=float,
                )
                reduced = hessian[np.ix_(free, free)]
                reduced.flat[:: reduced.shape[0] + 1] += 1e-8
                adjoint = np.linalg.solve(reduced.T, rhs)
            else:
                operator = LinearOperator(
                    (free.size, free.size),
                    matvec=reduced_hvp,
                    rmatvec=reduced_hvp,
                    dtype=float,
                )
                adjoint, status = cg(
                    operator,
                    rhs,
                    rtol=1e-8,
                    atol=1e-11,
                    maxiter=min(500, max(100, free.size)),
                )
                if status != 0:
                    adjoint, status = minres(
                        operator,
                        rhs,
                        rtol=1e-8,
                        maxiter=min(750, max(150, free.size)),
                    )
                if status != 0:
                    raise RuntimeError(
                        "OML quality adjoint tangent solve did not converge; "
                        f"status={status}."
                    )
            lambda_full[free] = np.asarray(adjoint, dtype=float)

        _, stationarity_pullback = jax.vjp(
            lambda current_coeff, current_candidate: gradient_function(
                z,
                current_coeff,
                current_candidate,
            ),
            coeff,
            candidate,
        )
        stationarity_coeff, stationarity_candidate = stationarity_pullback(
            jnp.asarray(lambda_full)
        )
        d_coefficients = tuple(
            np.asarray(direct - implicit, dtype=float)
            for direct, implicit in zip(
                direct_coeff,
                stationarity_coeff,
            )
        )
        d_candidate = np.asarray(
            direct_candidate - stationarity_candidate,
            dtype=float,
        )
        d_parametric = tuple(
            np.zeros_like(np.asarray(item, dtype=float))
            for item in parametric_coordinates
        )
        return d_candidate, d_parametric, d_coefficients


class OMLQualityOperation(csdl.experimental.CustomExplicitOperationBeta):
    """CSDL wrapper for :class:`OMLQualityModel`."""

    def __init__(
        self,
        model: OMLQualityModel,
        parameter_groups: Sequence[ParameterizedProjectionGroup],
    ):
        super().__init__()
        self.model = model
        self.parameter_groups = tuple(parameter_groups)

    def evaluate(self, candidate_vertices):
        self.declare_input("candidate_vertices", candidate_vertices)
        for index, group in enumerate(self.parameter_groups):
            self.declare_input(
                f"parametric_coordinates_{index}",
                group.parametric_coordinates,
            )
            self.declare_input(
                f"coefficients_{index}",
                group.coefficients,
            )
        output = self.create_output(
            "quality_vertices",
            (self.model.quality_vertex_ids.size, 3),
        )
        self.declare_vjp_function(
            OMLQualityVJP,
            model=self.model,
            parameter_groups=self.parameter_groups,
        )
        return output

    def compute(self, inputs, outputs):
        parametric = tuple(
            inputs[f"parametric_coordinates_{index}"]
            for index in range(len(self.parameter_groups))
        )
        coefficients = tuple(
            inputs[f"coefficients_{index}"]
            for index in range(len(self.parameter_groups))
        )
        repaired, _, info = self.model.solve(
            inputs["candidate_vertices"],
            parametric,
            coefficients,
            return_state=True,
        )
        outputs["quality_vertices"] = repaired
        if self.model.verbose:
            print(
                "[oml-quality] "
                f"vertices={info.quality_vertices} "
                f"support_cells={info.support_cells} "
                f"feasibility_iterations={info.feasibility_iterations} "
                f"quality_iterations={info.quality_iterations} "
                f"min_oriented_ratio={info.minimum_oriented_ratio:+.3e} "
                f"projected_gradient_inf={info.final_gradient_inf_norm:.3e} "
                f"active_bounds={info.active_bound_dofs} "
                f"converged={int(info.quality_solver_success)}",
                flush=True,
            )


class OMLQualityVJP(csdl.experimental.CustomExplicitOperationBeta):
    """IFT VJP of the converged fixed-branch OML quality equilibrium."""

    def __init__(
        self,
        model: OMLQualityModel,
        parameter_groups: Sequence[ParameterizedProjectionGroup],
    ):
        super().__init__()
        self.model = model
        self.parameter_groups = tuple(parameter_groups)

    def evaluate(self, inputs, d_outputs):
        candidate = inputs["candidate_vertices"]
        d_quality = d_outputs["quality_vertices"]
        self.declare_input("candidate_vertices", candidate)
        self.declare_input("d_quality_vertices", d_quality)
        d_candidate = self.create_output(
            "d_candidate_vertices",
            candidate.shape,
        )
        result = {"candidate_vertices": d_candidate}
        for index, _ in enumerate(self.parameter_groups):
            parametric = inputs[f"parametric_coordinates_{index}"]
            coefficients = inputs[f"coefficients_{index}"]
            self.declare_input(
                f"parametric_coordinates_{index}",
                parametric,
            )
            self.declare_input(f"coefficients_{index}", coefficients)
            d_parametric = self.create_output(
                f"d_parametric_coordinates_{index}",
                parametric.shape,
            )
            d_coefficients = self.create_output(
                f"d_coefficients_{index}",
                coefficients.shape,
            )
            result[f"parametric_coordinates_{index}"] = d_parametric
            result[f"coefficients_{index}"] = d_coefficients
        return result

    def compute(self, inputs, outputs):
        parametric = tuple(
            inputs[f"parametric_coordinates_{index}"]
            for index in range(len(self.parameter_groups))
        )
        coefficients = tuple(
            inputs[f"coefficients_{index}"]
            for index in range(len(self.parameter_groups))
        )
        d_candidate, d_parametric, d_coefficients = self.model.compute_vjp(
            inputs["candidate_vertices"],
            parametric,
            coefficients,
            inputs["d_quality_vertices"],
        )
        outputs["d_candidate_vertices"] = d_candidate
        for index in range(len(self.parameter_groups)):
            outputs[f"d_parametric_coordinates_{index}"] = d_parametric[index]
            outputs[f"d_coefficients_{index}"] = d_coefficients[index]


def optimize_mesh_on_oml(
    *,
    mesh,
    candidate_mesh_vertices,
    quality_vertex_ids: np.ndarray,
    parameter_groups: Sequence[ParameterizedProjectionGroup],
    **model_options,
):
    """Return the candidate mesh with a fixed set of rows quality-optimized."""

    model = OMLQualityModel(
        mesh,
        quality_vertex_ids=quality_vertex_ids,
        parameter_groups=parameter_groups,
        **model_options,
    )
    quality_vertices = OMLQualityOperation(
        model,
        parameter_groups,
    ).evaluate(candidate_mesh_vertices)
    ids = np.asarray(quality_vertex_ids, dtype=np.int64).reshape(-1)
    return candidate_mesh_vertices.set(_row_slice(ids), quality_vertices)


def _row_slice(rows):
    rows = np.asarray(rows, dtype=np.int64).reshape(-1)
    if rows.size == 1:
        row = int(rows[0])
        return csdl.slice[row : row + 1, :]
    return csdl.slice[rows.tolist(), :]


__all__ = [
    "OMLQualityModel",
    "OMLQualityOperation",
    "OMLQualitySolveInfo",
    "OMLQualityVJP",
    "optimize_mesh_on_oml",
    "select_fixed_vertex_band",
]
