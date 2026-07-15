from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .orthogonality_projection_numpy import (
    OrthogonalityNewtonParams,
    SurfaceProjectionResult,
    project_points_on_surface_edge_newton_numpy,
    project_points_orthogonality_newton_numpy,
)
from .warm_start_projections import (
    DEFAULT_FUN_SET_PATH,
    build_sampled_patches_mesh,
    warm_start_from_triangulation,
)


try:
    import lsdo_function_spaces as lfs
except Exception:  # pragma: no cover
    lfs = None

try:
    from lsdo_function_spaces.core.spaces.non_cython_bsplines.compute_basis_matrix_numpy_factory_patched import (
        make_bspline_evaluator_numpy,
    )
except Exception:  # pragma: no cover
    make_bspline_evaluator_numpy = None


EdgeName = str
POINT_CANDIDATE_AXIS = -2


@dataclass(frozen=True)
class NeighborEdgeMap:
    neighbor_patch: int
    neighbor_edge: EdgeName
    reverse_along_edge: bool = False


@dataclass
class WarmStartCandidateProjectionResult:
    patch_id: np.ndarray
    uv: np.ndarray
    projected_points: np.ndarray
    dist2: np.ndarray
    residual: np.ndarray
    converged: np.ndarray
    iterations: np.ndarray
    candidate_kind: List[str]
    warm_patch_id: np.ndarray
    warm_uv0: np.ndarray
    edge_map: Dict[Tuple[int, EdgeName], NeighborEdgeMap]


@dataclass(frozen=True)
class _CandidateSpec:
    point_index: int
    patch_id: int
    uv0: Tuple[float, float]
    fixed_axis: int
    fixed_value: float
    kind: str


def load_function_set_from_pickle(pickle_path: Path = DEFAULT_FUN_SET_PATH):
    if lfs is None:
        raise ImportError("lsdo_function_spaces is required to load a FunctionSet from pickle.")

    import pickle

    with open(pickle_path, "rb") as handle:
        function_data = pickle.load(handle)

    functions = {}
    for key, fun_data in function_data.items():
        space = lfs.BSplineSpaceNew(
            num_parametric_dimensions=2,
            degree=fun_data["degree"],
            coefficients_shape=fun_data["coefficients_shape"],
        )
        functions[int(key)] = lfs.Function(
            space=space,
            coefficients=fun_data["coefficients"],
        )

    return lfs.FunctionSet(functions=functions)


def _require_numpy_bspline_factory() -> None:
    if make_bspline_evaluator_numpy is None:
        raise ImportError(
            "make_bspline_evaluator_numpy not found; ensure "
            "compute_basis_matrix_numpy_factory_patched.py is on path."
        )


def _which_edge(u: float, v: float, eps: float) -> List[EdgeName]:
    edges: List[EdgeName] = []
    if u <= eps:
        edges.append("u0")
    if u >= 1.0 - eps:
        edges.append("u1")
    if v <= eps:
        edges.append("v0")
    if v >= 1.0 - eps:
        edges.append("v1")
    return edges


def _edges_by_distance(u: float, v: float) -> List[EdgeName]:
    distances = [
        (u, "u0"),
        (1.0 - u, "u1"),
        (v, "v0"),
        (1.0 - v, "v1"),
    ]
    distances.sort(key=lambda item: (item[0], item[1]))
    return [edge for _, edge in distances]


def _edge_distance(u: float, v: float, edge: EdgeName) -> float:
    if edge == "u0":
        return u
    if edge == "u1":
        return 1.0 - u
    if edge == "v0":
        return v
    if edge == "v1":
        return 1.0 - v
    raise ValueError(f"Unknown edge {edge}")


def _map_uv_across_edge(
    uv: np.ndarray,
    from_edge: EdgeName,
    to_edge: EdgeName,
    reverse_along_edge: bool,
) -> np.ndarray:
    u, v = float(uv[0]), float(uv[1])

    if from_edge in ("u0", "u1"):
        t = v
        if reverse_along_edge:
            t = 1.0 - t
        if to_edge == "u0":
            return np.array([0.0, t], dtype=float)
        if to_edge == "u1":
            return np.array([1.0, t], dtype=float)
        if to_edge == "v0":
            return np.array([t, 0.0], dtype=float)
        if to_edge == "v1":
            return np.array([t, 1.0], dtype=float)
    else:
        t = u
        if reverse_along_edge:
            t = 1.0 - t
        if to_edge == "u0":
            return np.array([0.0, t], dtype=float)
        if to_edge == "u1":
            return np.array([1.0, t], dtype=float)
        if to_edge == "v0":
            return np.array([t, 0.0], dtype=float)
        if to_edge == "v1":
            return np.array([t, 1.0], dtype=float)

    raise ValueError(f"Invalid edge mapping: {from_edge} -> {to_edge}")


def _edge_uv_samples(edge: EdgeName, num_samples: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, num_samples, dtype=float)
    if edge == "u0":
        return np.column_stack([np.zeros_like(t), t])
    if edge == "u1":
        return np.column_stack([np.ones_like(t), t])
    if edge == "v0":
        return np.column_stack([t, np.zeros_like(t)])
    if edge == "v1":
        return np.column_stack([t, np.ones_like(t)])
    raise ValueError(f"Unknown edge {edge}")


def _edge_to_constraint(edge: EdgeName) -> tuple[int, float]:
    if edge == "u0":
        return 0, 0.0
    if edge == "u1":
        return 0, 1.0
    if edge == "v0":
        return 1, 0.0
    if edge == "v1":
        return 1, 1.0
    raise ValueError(f"Unknown edge {edge}")


def _get_patch_metadata(function_set, patch_id: int):
    fun = function_set.functions[int(patch_id)]
    coeffs = np.asarray(fun.coefficients.value, dtype=float)
    degrees = tuple(int(v) for v in fun.space.degree)
    knot_vectors = tuple(np.asarray(k, dtype=float) for k in fun.space.knots)
    return coeffs, degrees, knot_vectors


def _append_candidate_spec(
    specs: List[_CandidateSpec],
    seen: set,
    *,
    point_index: int,
    candidate_patch: int,
    candidate_uv: np.ndarray,
    fixed_axis: int,
    fixed_value: float,
    kind: str,
) -> None:
    fixed_value_key = None if fixed_axis < 0 else round(float(fixed_value), 12)
    key = (
        int(candidate_patch),
        int(fixed_axis),
        fixed_value_key,
        round(float(candidate_uv[0]), 12),
        round(float(candidate_uv[1]), 12),
    )
    if key in seen:
        return
    seen.add(key)
    specs.append(
        _CandidateSpec(
            point_index=point_index,
            patch_id=int(candidate_patch),
            uv0=(float(candidate_uv[0]), float(candidate_uv[1])),
            fixed_axis=int(fixed_axis),
            fixed_value=float(fixed_value),
            kind=kind,
        )
    )


def _add_edge_candidate_specs(
    specs: List[_CandidateSpec],
    seen: set,
    *,
    point_index: int,
    patch_id: int,
    uv_seed: np.ndarray,
    edge: EdgeName,
    edge_map: Dict[Tuple[int, EdgeName], NeighborEdgeMap],
    degenerate_edge_map: Optional[Dict[Tuple[int, EdgeName], float]],
    include_current_patch_boundary: bool,
    include_neighbor_patch: bool,
    include_neighbor_boundary: bool,
    kind_prefix: str = "",
) -> None:
    current_edge_uv = _map_uv_across_edge(
        uv=uv_seed,
        from_edge=edge,
        to_edge=edge,
        reverse_along_edge=False,
    )
    fixed_axis, fixed_value = _edge_to_constraint(edge)
    edge_is_degenerate = degenerate_edge_map is not None and (patch_id, edge) in degenerate_edge_map

    if include_current_patch_boundary:
        if edge_is_degenerate:
            _append_candidate_spec(
                specs,
                seen,
                point_index=point_index,
                candidate_patch=patch_id,
                candidate_uv=current_edge_uv,
                fixed_axis=POINT_CANDIDATE_AXIS,
                fixed_value=np.nan,
                kind=f"{kind_prefix}current_{edge}_degenerate_point",
            )
        else:
            _append_candidate_spec(
                specs,
                seen,
                point_index=point_index,
                candidate_patch=patch_id,
                candidate_uv=current_edge_uv,
                fixed_axis=fixed_axis,
                fixed_value=fixed_value,
                kind=f"{kind_prefix}current_{edge}_boundary",
            )

    neighbor = edge_map.get((patch_id, edge))
    if neighbor is None:
        return

    mapped_uv = _map_uv_across_edge(
        uv=uv_seed,
        from_edge=edge,
        to_edge=neighbor.neighbor_edge,
        reverse_along_edge=neighbor.reverse_along_edge,
    )

    if include_neighbor_patch:
        _append_candidate_spec(
            specs,
            seen,
            point_index=point_index,
            candidate_patch=neighbor.neighbor_patch,
            candidate_uv=mapped_uv,
            fixed_axis=-1,
            fixed_value=np.nan,
            kind=f"{kind_prefix}neighbor_{edge}_patch",
        )

    if include_neighbor_boundary:
        nbr_axis, nbr_value = _edge_to_constraint(neighbor.neighbor_edge)
        neighbor_edge_is_degenerate = (
            degenerate_edge_map is not None
            and (neighbor.neighbor_patch, neighbor.neighbor_edge) in degenerate_edge_map
        )
        if neighbor_edge_is_degenerate:
            _append_candidate_spec(
                specs,
                seen,
                point_index=point_index,
                candidate_patch=neighbor.neighbor_patch,
                candidate_uv=mapped_uv,
                fixed_axis=POINT_CANDIDATE_AXIS,
                fixed_value=np.nan,
                kind=f"{kind_prefix}neighbor_{neighbor.neighbor_edge}_degenerate_point",
            )
        else:
            _append_candidate_spec(
                specs,
                seen,
                point_index=point_index,
                candidate_patch=neighbor.neighbor_patch,
                candidate_uv=mapped_uv,
                fixed_axis=nbr_axis,
                fixed_value=nbr_value,
                kind=f"{kind_prefix}neighbor_{neighbor.neighbor_edge}_boundary",
            )


def build_edge_neighbor_map(
    function_set,
    patch_indices: Optional[Iterable[int]] = None,
    *,
    num_samples: int = 41,
    atol: float = 1e-6,
    rtol: float = 1e-6,
) -> Dict[Tuple[int, EdgeName], NeighborEdgeMap]:
    _require_numpy_bspline_factory()

    if patch_indices is None:
        patch_indices = function_set.functions.keys()
    patch_indices = [int(idx) for idx in patch_indices]

    edge_points: Dict[Tuple[int, EdgeName], np.ndarray] = {}
    edge_keys: List[Tuple[int, EdgeName]] = []
    all_points: List[np.ndarray] = []

    evaluator_cache = {}
    for patch_id in patch_indices:
        coeffs, degrees, knot_vectors = _get_patch_metadata(function_set, patch_id)
        if patch_id not in evaluator_cache:
            evaluator_cache[patch_id] = make_bspline_evaluator_numpy(
                degrees=degrees,
                knot_vectors=knot_vectors,
                der_orders=None,
            )
        eval_S = evaluator_cache[patch_id]

        for edge in ("u0", "u1", "v0", "v1"):
            uv = _edge_uv_samples(edge, num_samples)
            xyz = np.asarray(eval_S(uv, coeffs), dtype=float)
            key = (patch_id, edge)
            edge_keys.append(key)
            edge_points[key] = xyz
            all_points.append(xyz)

    if not all_points:
        return {}

    stacked = np.vstack(all_points)
    diag = np.linalg.norm(stacked.max(axis=0) - stacked.min(axis=0))
    tol = max(float(atol), float(rtol) * float(diag))

    candidates = []
    for i, key_a in enumerate(edge_keys):
        xyz_a = edge_points[key_a]
        for j in range(i + 1, len(edge_keys)):
            key_b = edge_keys[j]
            if key_a[0] == key_b[0]:
                continue
            xyz_b = edge_points[key_b]

            forward_end = max(
                np.linalg.norm(xyz_a[0] - xyz_b[0]),
                np.linalg.norm(xyz_a[-1] - xyz_b[-1]),
            )
            reverse_end = max(
                np.linalg.norm(xyz_a[0] - xyz_b[-1]),
                np.linalg.norm(xyz_a[-1] - xyz_b[0]),
            )
            if min(forward_end, reverse_end) > tol:
                continue

            forward_score = np.max(np.linalg.norm(xyz_a - xyz_b, axis=1))
            reverse_score = np.max(np.linalg.norm(xyz_a - xyz_b[::-1], axis=1))
            reverse = reverse_score < forward_score
            score = reverse_score if reverse else forward_score

            if score <= tol:
                candidates.append((score, key_a, key_b, reverse))

    candidates.sort(key=lambda item: item[0])

    assigned = set()
    edge_map: Dict[Tuple[int, EdgeName], NeighborEdgeMap] = {}
    for _, key_a, key_b, reverse in candidates:
        if key_a in assigned or key_b in assigned:
            continue
        edge_map[key_a] = NeighborEdgeMap(
            neighbor_patch=int(key_b[0]),
            neighbor_edge=key_b[1],
            reverse_along_edge=reverse,
        )
        edge_map[key_b] = NeighborEdgeMap(
            neighbor_patch=int(key_a[0]),
            neighbor_edge=key_a[1],
            reverse_along_edge=reverse,
        )
        assigned.add(key_a)
        assigned.add(key_b)

    return edge_map


def _build_candidate_specs(
    patch_id: np.ndarray,
    uv0: np.ndarray,
    edge_map: Dict[Tuple[int, EdgeName], NeighborEdgeMap],
    degenerate_edge_map: Optional[Dict[Tuple[int, EdgeName], float]],
    *,
    eps_edge: float,
    include_current_patch_boundary: bool,
    include_neighbor_patch: bool,
    include_neighbor_boundary: bool,
) -> List[_CandidateSpec]:
    specs: List[_CandidateSpec] = []

    for point_index in range(patch_id.shape[0]):
        pid = int(patch_id[point_index])
        uv_seed = np.asarray(uv0[point_index], dtype=float)
        seen = set()
        edges_added = set()

        _append_candidate_spec(
            specs,
            seen,
            point_index=point_index,
            candidate_patch=pid,
            candidate_uv=uv_seed,
            fixed_axis=-1,
            fixed_value=np.nan,
            kind="warm_start_patch",
        )

        for edge in _which_edge(float(uv_seed[0]), float(uv_seed[1]), eps_edge):
            edges_added.add(edge)
            _add_edge_candidate_specs(
                specs,
                seen,
                point_index=point_index,
                patch_id=pid,
                uv_seed=uv_seed,
                edge=edge,
                edge_map=edge_map,
                degenerate_edge_map=degenerate_edge_map,
                include_current_patch_boundary=include_current_patch_boundary,
                include_neighbor_patch=include_neighbor_patch,
                include_neighbor_boundary=include_neighbor_boundary,
            )

        if degenerate_edge_map is not None:
            degenerate_threshold = 2.0 * eps_edge
            for edge in _edges_by_distance(float(uv_seed[0]), float(uv_seed[1])):
                if edge in edges_added:
                    continue
                if (pid, edge) not in degenerate_edge_map:
                    continue
                if _edge_distance(float(uv_seed[0]), float(uv_seed[1]), edge) > degenerate_threshold:
                    break
                _add_edge_candidate_specs(
                    specs,
                    seen,
                    point_index=point_index,
                    patch_id=pid,
                    uv_seed=uv_seed,
                    edge=edge,
                    edge_map=edge_map,
                    degenerate_edge_map=degenerate_edge_map,
                    include_current_patch_boundary=include_current_patch_boundary,
                    include_neighbor_patch=include_neighbor_patch,
                    include_neighbor_boundary=include_neighbor_boundary,
                )

    return specs


def _build_retry_candidate_specs(
    warm_patch_id: np.ndarray,
    warm_uv0: np.ndarray,
    point_indices: np.ndarray,
    edge_map: Dict[Tuple[int, EdgeName], NeighborEdgeMap],
    degenerate_edge_map: Optional[Dict[Tuple[int, EdgeName], float]],
    *,
    retry_num_closest_edges: int,
    include_current_patch_boundary: bool,
    include_neighbor_patch: bool,
    include_neighbor_boundary: bool,
) -> List[_CandidateSpec]:
    specs: List[_CandidateSpec] = []
    num_edges = max(1, int(retry_num_closest_edges))

    for point_index in np.asarray(point_indices, dtype=int):
        pid = int(warm_patch_id[point_index])
        uv_seed = np.asarray(warm_uv0[point_index], dtype=float)
        seen = set()

        for edge in _edges_by_distance(float(uv_seed[0]), float(uv_seed[1]))[:num_edges]:
            _add_edge_candidate_specs(
                specs,
                seen,
                point_index=point_index,
                patch_id=pid,
                uv_seed=uv_seed,
                edge=edge,
                edge_map=edge_map,
                degenerate_edge_map=degenerate_edge_map,
                include_current_patch_boundary=include_current_patch_boundary,
                include_neighbor_patch=include_neighbor_patch,
                include_neighbor_boundary=include_neighbor_boundary,
                kind_prefix="retry_",
            )

    return specs


def _build_local_retry_candidate_specs(
    selected_patch_id: np.ndarray,
    selected_uv: np.ndarray,
    point_indices: np.ndarray,
    *,
    uv_step: float,
) -> List[_CandidateSpec]:
    specs: List[_CandidateSpec] = []
    step = max(float(uv_step), 1e-12)
    offsets = np.array(
        [
            [0.0, 0.0],
            [-step, 0.0],
            [step, 0.0],
            [0.0, -step],
            [0.0, step],
            [-step, -step],
            [-step, step],
            [step, -step],
            [step, step],
        ],
        dtype=float,
    )

    for point_index in np.asarray(point_indices, dtype=int):
        pid = int(selected_patch_id[point_index])
        uv_seed = np.asarray(selected_uv[point_index], dtype=float)
        seen = set()
        for offset in offsets:
            candidate_uv = np.clip(uv_seed + offset, 0.0, 1.0)
            _append_candidate_spec(
                specs,
                seen,
                point_index=point_index,
                candidate_patch=pid,
                candidate_uv=candidate_uv,
                fixed_axis=-1,
                fixed_value=0.0,
                kind="retry_local_patch",
            )

    return specs


def _run_candidate_projections(
    function_set,
    points: np.ndarray,
    specs: Sequence[_CandidateSpec],
    params: OrthogonalityNewtonParams,
) -> Dict[str, object]:
    num_candidates = len(specs)
    if num_candidates == 0:
        raise ValueError("No candidate projection specs were generated.")

    point_index = np.array([spec.point_index for spec in specs], dtype=int)
    patch_id = np.array([spec.patch_id for spec in specs], dtype=int)
    uv0 = np.array([spec.uv0 for spec in specs], dtype=float)
    fixed_axis = np.array([spec.fixed_axis for spec in specs], dtype=int)
    fixed_value = np.array([spec.fixed_value for spec in specs], dtype=float)
    candidate_kind = [spec.kind for spec in specs]

    projected_points = np.zeros((num_candidates, points.shape[1]), dtype=float)
    final_uv = np.zeros((num_candidates, 2), dtype=float)
    dist2 = np.full((num_candidates,), np.inf, dtype=float)
    residual = np.full((num_candidates,), np.inf, dtype=float)
    converged = np.zeros((num_candidates,), dtype=bool)
    iterations = np.zeros((num_candidates,), dtype=int)

    groups: Dict[Tuple[int, int, float], List[int]] = {}
    for candidate_index in range(num_candidates):
        key = (
            int(patch_id[candidate_index]),
            int(fixed_axis[candidate_index]),
            float(fixed_value[candidate_index]) if fixed_axis[candidate_index] >= 0 else None,
        )
        groups.setdefault(key, []).append(candidate_index)

    patch_cache = {}
    for (candidate_patch, candidate_fixed_axis, candidate_fixed_value), group_indices in groups.items():
        if candidate_patch not in patch_cache:
            patch_cache[candidate_patch] = _get_patch_metadata(function_set, candidate_patch)
        coeffs, degrees, knot_vectors = patch_cache[candidate_patch]

        group_indices = np.asarray(group_indices, dtype=int)
        group_points = points[point_index[group_indices]]
        group_uv0 = uv0[group_indices]

        if candidate_fixed_axis < 0:
            if candidate_fixed_axis == POINT_CANDIDATE_AXIS:
                evaluator = make_bspline_evaluator_numpy(
                    degrees=degrees,
                    knot_vectors=knot_vectors,
                    der_orders=None,
                )
                point_xyz = np.asarray(evaluator(group_uv0, coeffs), dtype=float)
                diff = point_xyz - group_points
                result = SurfaceProjectionResult(
                    uv=group_uv0.copy(),
                    projected_points=point_xyz,
                    residual=np.zeros((group_indices.shape[0],), dtype=float),
                    step_norm=np.zeros((group_indices.shape[0],), dtype=float),
                    dist2=np.einsum("ij,ij->i", diff, diff),
                    converged=np.ones((group_indices.shape[0],), dtype=bool),
                    iterations=np.zeros((group_indices.shape[0],), dtype=int),
                )
            else:
                result = project_points_orthogonality_newton_numpy(
                    group_points,
                    group_uv0,
                    coeffs,
                    degrees,
                    knot_vectors,
                    params=params,
                )
        else:
            free_axis = 1 - candidate_fixed_axis
            result = project_points_on_surface_edge_newton_numpy(
                group_points,
                group_uv0[:, free_axis],
                coeffs,
                degrees,
                knot_vectors,
                fixed_axis=candidate_fixed_axis,
                fixed_value=candidate_fixed_value,
                params=params,
            )

        projected_points[group_indices] = result.projected_points
        final_uv[group_indices] = result.uv
        dist2[group_indices] = result.dist2
        residual[group_indices] = result.residual
        converged[group_indices] = result.converged
        iterations[group_indices] = result.iterations

    return {
        "point_index": point_index,
        "patch_id": patch_id,
        "uv": final_uv,
        "projected_points": projected_points,
        "dist2": dist2,
        "residual": residual,
        "converged": converged,
        "iterations": iterations,
        "candidate_kind": candidate_kind,
    }


def _is_candidate_better(
    converged: bool,
    residual: float,
    dist2: float,
    best_converged: bool,
    best_residual: float,
    best_dist2: float,
) -> bool:
    rank = 0 if converged else 1
    best_rank = 0 if best_converged else 1

    if rank < best_rank:
        return True
    if rank > best_rank:
        return False
    if rank == 0:
        if dist2 < best_dist2:
            return True
        if dist2 > best_dist2:
            return False
        return residual < best_residual
    if residual < best_residual:
        return True
    if residual > best_residual:
        return False
    return dist2 < best_dist2


def _compute_candidate_normal(
    function_set,
    patch_id: int,
    uv: np.ndarray,
) -> np.ndarray:
    _require_numpy_bspline_factory()
    coeffs, degrees, knot_vectors = _get_patch_metadata(function_set, int(patch_id))
    uv = np.asarray(uv, dtype=float).reshape(1, 2)
    evaluator_u = make_bspline_evaluator_numpy(
        degrees=degrees,
        knot_vectors=knot_vectors,
        der_orders=(1, 0),
    )
    evaluator_v = make_bspline_evaluator_numpy(
        degrees=degrees,
        knot_vectors=knot_vectors,
        der_orders=(0, 1),
    )
    tangent_u = np.asarray(evaluator_u(uv, coeffs), dtype=float).reshape(1, -1)[0]
    tangent_v = np.asarray(evaluator_v(uv, coeffs), dtype=float).reshape(1, -1)[0]
    if tangent_u.size != 3 or tangent_v.size != 3:
        return np.zeros(3, dtype=float)
    normal = np.cross(tangent_u, tangent_v)
    norm = np.linalg.norm(normal)
    if norm <= 1e-14:
        return np.zeros(3, dtype=float)
    return normal / norm


def _is_retry_candidate_compatible(
    function_set,
    *,
    selected_patch_id: int,
    selected_uv: np.ndarray,
    selected_dist2: float,
    retry_patch_id: int,
    retry_uv: np.ndarray,
    retry_dist2: float,
    retry_accept_distance_factor: float,
    retry_accept_distance_atol: float,
    retry_normal_dot_min: float,
) -> bool:
    if not np.isfinite(retry_dist2):
        return False
    if not np.isfinite(selected_dist2):
        return True

    selected_distance = float(np.sqrt(max(float(selected_dist2), 0.0)))
    retry_distance = float(np.sqrt(max(float(retry_dist2), 0.0)))
    distance_limit = (
        max(float(retry_accept_distance_factor), 1.0) * selected_distance
        + max(float(retry_accept_distance_atol), 0.0)
    )
    if retry_distance > distance_limit:
        return False

    if int(selected_patch_id) == int(retry_patch_id):
        return True

    if retry_normal_dot_min <= -1.0:
        return True

    selected_normal = _compute_candidate_normal(
        function_set,
        int(selected_patch_id),
        selected_uv,
    )
    retry_normal = _compute_candidate_normal(
        function_set,
        int(retry_patch_id),
        retry_uv,
    )
    if np.linalg.norm(selected_normal) <= 0.0 or np.linalg.norm(retry_normal) <= 0.0:
        return True

    return float(np.dot(selected_normal, retry_normal)) >= float(retry_normal_dot_min)


def _select_best_candidates(candidate_results: Dict[str, object], num_points: int) -> np.ndarray:
    point_index = candidate_results["point_index"]
    dist2 = candidate_results["dist2"]
    residual = candidate_results["residual"]
    converged = candidate_results["converged"]

    best_candidate = np.full((num_points,), -1, dtype=int)
    best_rank = np.full((num_points,), 2, dtype=int)
    best_residual = np.full((num_points,), np.inf, dtype=float)
    best_dist2 = np.full((num_points,), np.inf, dtype=float)

    for candidate_index in range(point_index.shape[0]):
        original_point = point_index[candidate_index]
        rank = 0 if converged[candidate_index] else 1

        better = False
        if rank < best_rank[original_point]:
            better = True
        elif rank == best_rank[original_point]:
            if rank == 0:
                if dist2[candidate_index] < best_dist2[original_point]:
                    better = True
                elif (
                    dist2[candidate_index] == best_dist2[original_point]
                    and residual[candidate_index] < best_residual[original_point]
                ):
                    better = True
            else:
                if residual[candidate_index] < best_residual[original_point]:
                    better = True
                elif (
                    residual[candidate_index] == best_residual[original_point]
                    and dist2[candidate_index] < best_dist2[original_point]
                ):
                    better = True

        if better:
            best_candidate[original_point] = candidate_index
            best_rank[original_point] = rank
            best_residual[original_point] = residual[candidate_index]
            best_dist2[original_point] = dist2[candidate_index]

    return best_candidate


def project_points_with_warm_start_candidates_numpy(
    function_set,
    points: np.ndarray,
    *,
    patch_indices: Optional[Iterable[int]] = None,
    mesh=None,
    warm_start_nu: int = 100,
    warm_start_nv: int = 100,
    edge_map: Optional[Dict[Tuple[int, EdgeName], NeighborEdgeMap]] = None,
    degenerate_edge_map: Optional[Dict[Tuple[int, EdgeName], float]] = None,
    edge_map_num_samples: int = 41,
    edge_map_atol: float = 1e-6,
    edge_map_rtol: float = 1e-6,
    eps_edge: float = 0.005,
    include_current_patch_boundary: bool = True,
    include_neighbor_patch: bool = True,
    include_neighbor_boundary: bool = True,
    retry_on_failure: bool = True,
    retry_num_closest_edges: int = 2,
    retry_local_search: bool = True,
    retry_local_step_factor: float = 2.0,
    retry_accept_distance_factor: float = 4.0,
    retry_accept_distance_atol: float = 1e-3,
    retry_normal_dot_min: float = -0.25,
    params: OrthogonalityNewtonParams = OrthogonalityNewtonParams(),
) -> WarmStartCandidateProjectionResult:
    points = np.asarray(points, dtype=float)
    if points.ndim != 2:
        raise ValueError(f"points must have shape (M, phys_dim); got {points.shape}")

    if patch_indices is None:
        patch_indices = sorted(int(idx) for idx in function_set.functions.keys())
    else:
        patch_indices = [int(idx) for idx in patch_indices]

    if mesh is None:
        mesh = build_sampled_patches_mesh(
            function_set=function_set,
            patch_indices=patch_indices,
            Nu=warm_start_nu,
            Nv=warm_start_nv,
        )

    warm = warm_start_from_triangulation(mesh=mesh, points=points)

    if edge_map is None:
        edge_map = build_edge_neighbor_map(
            function_set=function_set,
            patch_indices=patch_indices,
            num_samples=edge_map_num_samples,
            atol=edge_map_atol,
            rtol=edge_map_rtol,
        )

    specs = _build_candidate_specs(
        patch_id=warm.patch_id,
        uv0=warm.uv0,
        edge_map=edge_map,
        degenerate_edge_map=degenerate_edge_map,
        eps_edge=eps_edge,
        include_current_patch_boundary=include_current_patch_boundary,
        include_neighbor_patch=include_neighbor_patch,
        include_neighbor_boundary=include_neighbor_boundary,
    )

    candidate_results = _run_candidate_projections(
        function_set=function_set,
        points=points,
        specs=specs,
        params=params,
    )
    best_candidate = _select_best_candidates(candidate_results, num_points=points.shape[0])

    selected_patch_id = candidate_results["patch_id"][best_candidate]
    selected_uv = candidate_results["uv"][best_candidate]
    selected_projected_points = candidate_results["projected_points"][best_candidate]
    selected_dist2 = candidate_results["dist2"][best_candidate]
    selected_residual = candidate_results["residual"][best_candidate]
    selected_converged = candidate_results["converged"][best_candidate]
    selected_iterations = candidate_results["iterations"][best_candidate]
    selected_kind = [candidate_results["candidate_kind"][idx] for idx in best_candidate]

    failed_points = np.where(~selected_converged)[0]
    if retry_on_failure and failed_points.size > 0:
        retry_specs: List[_CandidateSpec] = []
        if retry_local_search:
            retry_specs.extend(
                _build_local_retry_candidate_specs(
                    selected_patch_id,
                    selected_uv,
                    failed_points,
                    uv_step=max(float(retry_local_step_factor), 0.0) * max(float(eps_edge), 1e-12),
                )
            )
        retry_specs.extend(
            _build_retry_candidate_specs(
                warm_patch_id=warm.patch_id,
                warm_uv0=warm.uv0,
                point_indices=failed_points,
                edge_map=edge_map,
                degenerate_edge_map=degenerate_edge_map,
                retry_num_closest_edges=retry_num_closest_edges,
                include_current_patch_boundary=include_current_patch_boundary,
                include_neighbor_patch=include_neighbor_patch,
                include_neighbor_boundary=include_neighbor_boundary,
            )
        )

        if retry_specs:
            retry_results = _run_candidate_projections(
                function_set=function_set,
                points=points,
                specs=retry_specs,
                params=params,
            )
            retry_best = _select_best_candidates(retry_results, num_points=points.shape[0])

            for point_index in failed_points:
                retry_index = retry_best[point_index]
                if retry_index < 0:
                    continue

                if _is_candidate_better(
                    converged=bool(retry_results["converged"][retry_index]),
                    residual=float(retry_results["residual"][retry_index]),
                    dist2=float(retry_results["dist2"][retry_index]),
                    best_converged=bool(selected_converged[point_index]),
                    best_residual=float(selected_residual[point_index]),
                    best_dist2=float(selected_dist2[point_index]),
                ) and _is_retry_candidate_compatible(
                    function_set,
                    selected_patch_id=int(selected_patch_id[point_index]),
                    selected_uv=selected_uv[point_index],
                    selected_dist2=float(selected_dist2[point_index]),
                    retry_patch_id=int(retry_results["patch_id"][retry_index]),
                    retry_uv=retry_results["uv"][retry_index],
                    retry_dist2=float(retry_results["dist2"][retry_index]),
                    retry_accept_distance_factor=retry_accept_distance_factor,
                    retry_accept_distance_atol=retry_accept_distance_atol,
                    retry_normal_dot_min=retry_normal_dot_min,
                ):
                    selected_patch_id[point_index] = retry_results["patch_id"][retry_index]
                    selected_uv[point_index] = retry_results["uv"][retry_index]
                    selected_projected_points[point_index] = retry_results["projected_points"][retry_index]
                    selected_dist2[point_index] = retry_results["dist2"][retry_index]
                    selected_residual[point_index] = retry_results["residual"][retry_index]
                    selected_converged[point_index] = retry_results["converged"][retry_index]
                    selected_iterations[point_index] = retry_results["iterations"][retry_index]
                    selected_kind[point_index] = retry_results["candidate_kind"][retry_index]

    return WarmStartCandidateProjectionResult(
        patch_id=selected_patch_id,
        uv=selected_uv,
        projected_points=selected_projected_points,
        dist2=selected_dist2,
        residual=selected_residual,
        converged=selected_converged,
        iterations=selected_iterations,
        candidate_kind=selected_kind,
        warm_patch_id=np.asarray(warm.patch_id, dtype=int),
        warm_uv0=np.asarray(warm.uv0, dtype=float),
        edge_map=edge_map,
    )
