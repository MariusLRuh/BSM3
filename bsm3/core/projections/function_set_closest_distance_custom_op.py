from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_PACKAGES_DIR = Path(__file__).resolve().parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

for _package_name in ("CSDL_alpha", "lsdo_function_spaces"):
    _package_root = _PACKAGES_DIR / _package_name
    if _package_root.is_dir():
        _package_root_str = str(_package_root)
        if _package_root_str not in sys.path:
            sys.path.insert(0, _package_root_str)

try:
    import joblib  # noqa: F401
except Exception:
    _joblib_stub = types.ModuleType("joblib")

    def _delayed(func):
        def wrapper(*args, **kwargs):
            return lambda: func(*args, **kwargs)

        return wrapper

    class _Parallel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __call__(self, tasks):
            return [task() for task in tasks]

    _joblib_stub.delayed = _delayed
    _joblib_stub.Parallel = _Parallel
    sys.modules["joblib"] = _joblib_stub

import csdl_alpha as csdl
import numpy as np
import pyvista as pv

from lsdo_function_spaces.core.spaces.non_cython_bsplines.compute_basis_matrix_numpy_factory_patched import (
    apply_basis_stencil_numpy,
    compute_basis_stencil_numpy,
    make_bspline_evaluator_numpy,
    make_bspline_space_cache,
)

try:
    from .orthogonality_projection_numpy import OrthogonalityNewtonParams
    from .warm_start_candidate_projection_numpy import (
        NeighborEdgeMap,
        build_edge_neighbor_map,
        project_points_with_warm_start_candidates_numpy,
    )
    from .warm_start_projections import build_sampled_patches_mesh
except ImportError:
    from bsm3.core.projections.orthogonality_projection_numpy import OrthogonalityNewtonParams
    from bsm3.core.projections.warm_start_candidate_projection_numpy import (
        NeighborEdgeMap,
        build_edge_neighbor_map,
        project_points_with_warm_start_candidates_numpy,
    )
    from bsm3.core.projections.warm_start_projections import build_sampled_patches_mesh


@dataclass(frozen=True)
class PatchInfo:
    patch_id: int
    degrees: Tuple[int, ...]
    knot_vectors: Tuple[np.ndarray, ...]
    coefficient_shape: Tuple[int, ...]
    start: int
    stop: int
    space_cache: object
    mesh_vertex_indices: np.ndarray
    mesh_cols: np.ndarray
    mesh_weights: np.ndarray
    edge_vertex_indices: Dict[str, np.ndarray]


@dataclass
class _CoefficientHolder:
    value: np.ndarray


@dataclass(frozen=True)
class _SpaceView:
    degree: Tuple[int, ...]
    knots: Tuple[np.ndarray, ...]
    num_parametric_dimensions: int


@dataclass
class _FunctionView:
    space: _SpaceView
    coefficients: _CoefficientHolder


def stack_function_set_coefficients(function_set, patch_ids: Optional[Iterable[int]] = None) -> np.ndarray:
    if patch_ids is None:
        patch_ids = sorted(int(idx) for idx in function_set.functions.keys())
    else:
        patch_ids = [int(idx) for idx in patch_ids]

    stacked_blocks = []
    for patch_id in patch_ids:
        coeffs = np.asarray(function_set.functions[patch_id].coefficients.value, dtype=float)
        stacked_blocks.append(coeffs.reshape(-1, coeffs.shape[-1]))
    return np.vstack(stacked_blocks)


def _parse_fixed_axis(candidate_kind: str) -> Optional[int]:
    if "u0_boundary" in candidate_kind or "u1_boundary" in candidate_kind:
        return 0
    if "v0_boundary" in candidate_kind or "v1_boundary" in candidate_kind:
        return 1
    return None


def _is_point_candidate(candidate_kind: str) -> bool:
    return "degenerate_point" in candidate_kind


def _solve_2x2_batch(A: np.ndarray, b: np.ndarray, det_eps: float) -> np.ndarray:
    det = A[:, 0, 0] * A[:, 1, 1] - A[:, 0, 1] * A[:, 1, 0]
    x = np.zeros_like(b)

    good = np.abs(det) > det_eps
    if np.any(good):
        inv00 = A[good, 1, 1] / det[good]
        inv01 = -A[good, 0, 1] / det[good]
        inv10 = -A[good, 1, 0] / det[good]
        inv11 = A[good, 0, 0] / det[good]
        x[good, 0] = inv00 * b[good, 0] + inv01 * b[good, 1]
        x[good, 1] = inv10 * b[good, 0] + inv11 * b[good, 1]

    bad = np.where(~good)[0]
    for idx in bad:
        try:
            x[idx] = np.linalg.solve(A[idx], b[idx])
        except np.linalg.LinAlgError:
            x[idx] = 0.0

    return x


def _solve_reduced_linear_system(
    A: np.ndarray,
    rhs: np.ndarray,
    free_mask: np.ndarray,
    diag_eps: float,
    det_eps: float,
) -> np.ndarray:
    solution = np.zeros_like(rhs)

    both_free = free_mask[:, 0] & free_mask[:, 1]
    first_only = free_mask[:, 0] & ~free_mask[:, 1]
    second_only = ~free_mask[:, 0] & free_mask[:, 1]

    if np.any(both_free):
        solution[both_free] = _solve_2x2_batch(A[both_free], rhs[both_free], det_eps=det_eps)

    if np.any(first_only):
        denom = A[first_only, 0, 0]
        good = np.abs(denom) > diag_eps
        if np.any(good):
            idx = np.where(first_only)[0][good]
            solution[idx, 0] = rhs[idx, 0] / denom[good]

    if np.any(second_only):
        denom = A[second_only, 1, 1]
        good = np.abs(denom) > diag_eps
        if np.any(good):
            idx = np.where(second_only)[0][good]
            solution[idx, 1] = rhs[idx, 1] / denom[good]

    return solution


class _MutableFunctionSetWrapper:
    def __init__(self, patch_infos: Dict[int, PatchInfo]):
        self.patch_infos = patch_infos
        self.functions: Dict[int, _FunctionView] = {}
        self._evaluators: Dict[int, object] = {}

        for patch_id, info in patch_infos.items():
            self.functions[patch_id] = _FunctionView(
                space=_SpaceView(
                    degree=info.degrees,
                    knots=info.knot_vectors,
                    num_parametric_dimensions=len(info.degrees),
                ),
                coefficients=_CoefficientHolder(
                    value=np.zeros(info.coefficient_shape, dtype=float),
                ),
            )
            self._evaluators[patch_id] = make_bspline_evaluator_numpy(
                degrees=info.degrees,
                knot_vectors=info.knot_vectors,
                der_orders=None,
            )

    def update_coefficients(self, stacked_coefficients: np.ndarray) -> None:
        for patch_id, info in self.patch_infos.items():
            coeffs = np.asarray(stacked_coefficients[info.start:info.stop], dtype=float)
            self.functions[patch_id].coefficients.value = coeffs.reshape(info.coefficient_shape)

    def evaluate(self, parametric_coordinates, non_csdl=True, plot=False):
        del non_csdl, plot

        num_points = len(parametric_coordinates)
        output = np.zeros((num_points, self.functions[next(iter(self.functions))].coefficients.value.shape[-1]))

        grouped: Dict[int, List[Tuple[int, np.ndarray]]] = {}
        for point_index, (patch_id, uv) in enumerate(parametric_coordinates):
            grouped.setdefault(int(patch_id), []).append((point_index, np.asarray(uv, dtype=float)))

        for patch_id, items in grouped.items():
            indices = np.array([item[0] for item in items], dtype=int)
            uv = np.vstack([item[1] for item in items])
            coeffs = self.functions[patch_id].coefficients.value
            output[indices] = np.asarray(self._evaluators[patch_id](uv, coeffs), dtype=float)

        return output


class FunctionSetProjectionModel:
    def __init__(
        self,
        function_set,
        *,
        patch_indices: Optional[Iterable[int]] = None,
        warm_start_nu: int = 150,
        warm_start_nv: int = 150,
        edge_map_num_samples: int = 41,
        edge_map_atol: float = 1e-6,
        edge_map_rtol: float = 1e-6,
        eps_edge: Optional[float] = None,
        include_current_patch_boundary: bool = True,
        include_neighbor_patch: bool = True,
        include_neighbor_boundary: bool = True,
        retry_on_failure: bool = True,
        retry_num_closest_edges: int = 2,
        output_mode: str = "distance",
        sdf: bool = False,
        regularization_epsilon: float = 1e-8,
        params: OrthogonalityNewtonParams = OrthogonalityNewtonParams(),
        distance_eps: float = 1e-14,
        sdf_clean_tolerance: float = 1e-10,
        sdf_enclosed_tolerance: float = 1e-9,
        degenerate_edge_length_atol: float = 1e-10,
        degenerate_edge_length_rtol: float = 1e-8,
        degenerate_normal_tol: float = 1e-12,
        debug: bool = False,
    ):
        if patch_indices is None:
            patch_indices = sorted(int(idx) for idx in function_set.functions.keys())
        else:
            patch_indices = [int(idx) for idx in patch_indices]

        self.patch_ids = tuple(patch_indices)
        self.params = params
        self.distance_eps = float(distance_eps)
        self.include_current_patch_boundary = bool(include_current_patch_boundary)
        self.include_neighbor_patch = bool(include_neighbor_patch)
        self.include_neighbor_boundary = bool(include_neighbor_boundary)
        self.retry_on_failure = bool(retry_on_failure)
        self.retry_num_closest_edges = int(retry_num_closest_edges)
        self.output_mode = str(output_mode)
        self.sdf = bool(sdf)
        if self.output_mode not in ("distance", "squared_distance", "regularized_distance"):
            raise ValueError(
                "output_mode must be one of 'distance', 'squared_distance', or "
                f"'regularized_distance'; got {self.output_mode!r}."
            )
        self.regularization_epsilon = float(regularization_epsilon)
        if self.regularization_epsilon <= 0.0 and self.output_mode == "regularized_distance":
            raise ValueError("regularization_epsilon must be positive for regularized_distance mode.")
        if eps_edge is None:
            du = 1.0 / max(1, warm_start_nu - 1)
            dv = 1.0 / max(1, warm_start_nv - 1)
            eps_edge = 0.5 * max(du, dv)
        self.eps_edge = float(eps_edge)
        self.sdf_clean_tolerance = float(sdf_clean_tolerance)
        self.sdf_enclosed_tolerance = float(sdf_enclosed_tolerance)
        self.degenerate_edge_length_atol = float(degenerate_edge_length_atol)
        self.degenerate_edge_length_rtol = float(degenerate_edge_length_rtol)
        self.degenerate_normal_tol = float(degenerate_normal_tol)
        self.debug = bool(debug)
        template_mesh = build_sampled_patches_mesh(
            function_set=function_set,
            patch_indices=self.patch_ids,
            Nu=warm_start_nu,
            Nv=warm_start_nv,
        )
        self.mesh_faces = np.asarray(template_mesh.faces, dtype=np.int64)
        self.mesh_patch_id = np.asarray(template_mesh.point_data["patch_id"], dtype=np.int32)
        self.mesh_u = np.asarray(template_mesh.point_data["u"], dtype=float)
        self.mesh_v = np.asarray(template_mesh.point_data["v"], dtype=float)
        self.mesh_uv = np.column_stack([self.mesh_u, self.mesh_v])

        first_patch = function_set.functions[self.patch_ids[0]]
        self.physical_dimension = int(np.asarray(first_patch.coefficients.value).shape[-1])
        if self.sdf and self.physical_dimension != 3:
            raise ValueError(
                "sdf mode currently requires a 3D physical embedding; "
                f"got physical_dimension={self.physical_dimension}."
            )

        patch_infos: Dict[int, PatchInfo] = {}
        start = 0
        for patch_id in self.patch_ids:
            fun = function_set.functions[int(patch_id)]
            coeffs = np.asarray(fun.coefficients.value, dtype=float)
            coeff_shape = tuple(int(v) for v in coeffs.shape)
            num_ctrl = int(np.prod(coeff_shape[:-1]))
            stop = start + num_ctrl

            degrees = tuple(int(v) for v in fun.space.degree)
            knot_vectors = tuple(np.asarray(k, dtype=float) for k in fun.space.knots)
            space_cache = make_bspline_space_cache(degrees, knot_vectors)

            mesh_vertex_indices = np.where(self.mesh_patch_id == int(patch_id))[0]
            mesh_uv_patch = self.mesh_uv[mesh_vertex_indices]
            mesh_cols, mesh_weights, _ = compute_basis_stencil_numpy(
                mesh_uv_patch,
                degrees,
                knot_vectors,
                cache=space_cache,
            )
            mesh_vertex_grid = mesh_vertex_indices.reshape(warm_start_nu, warm_start_nv)
            edge_vertex_indices = {
                "u0": mesh_vertex_grid[0, :].copy(),
                "u1": mesh_vertex_grid[-1, :].copy(),
                "v0": mesh_vertex_grid[:, 0].copy(),
                "v1": mesh_vertex_grid[:, -1].copy(),
            }

            patch_infos[int(patch_id)] = PatchInfo(
                patch_id=int(patch_id),
                degrees=degrees,
                knot_vectors=knot_vectors,
                coefficient_shape=coeff_shape,
                start=start,
                stop=stop,
                space_cache=space_cache,
                mesh_vertex_indices=mesh_vertex_indices,
                mesh_cols=mesh_cols,
                mesh_weights=mesh_weights,
                edge_vertex_indices=edge_vertex_indices,
            )
            start = stop

        self.patch_infos = patch_infos
        self.total_num_control_points = start
        self.edge_map: Dict[Tuple[int, str], NeighborEdgeMap] = build_edge_neighbor_map(
            function_set=function_set,
            patch_indices=self.patch_ids,
            num_samples=edge_map_num_samples,
            atol=edge_map_atol,
            rtol=edge_map_rtol,
        )
        self.function_set_wrapper = _MutableFunctionSetWrapper(self.patch_infos)

    def _compute_output_measure(
        self,
        raw_distance: np.ndarray,
        raw_dist2: np.ndarray,
        zero_distance_mask: np.ndarray,
        sign: np.ndarray,
    ) -> np.ndarray:
        if self.output_mode == "distance":
            output_measure = raw_distance.copy()
        elif self.output_mode == "squared_distance":
            output_measure = raw_dist2.copy()
        elif self.output_mode == "regularized_distance":
            output_measure = np.sqrt(raw_dist2 + self.regularization_epsilon**2) - self.regularization_epsilon
        else:  # pragma: no cover
            raise RuntimeError(f"Unsupported output mode {self.output_mode!r}.")

        if self.sdf:
            output_measure *= sign
        output_measure[zero_distance_mask] = 0.0
        return output_measure

    def _compute_output_gradient_wrt_residual(
        self,
        residual_vector: np.ndarray,
        raw_distance: np.ndarray,
        raw_dist2: np.ndarray,
        zero_distance_mask: np.ndarray,
        sign: np.ndarray,
        outward_normals: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        gradient = np.zeros_like(residual_vector)
        active = ~zero_distance_mask

        if self.output_mode == "distance":
            safe = active & (raw_distance > self.distance_eps)
            gradient[safe] = residual_vector[safe] / raw_distance[safe, None]
            if self.sdf:
                gradient[safe] *= sign[safe, None]
                if outward_normals is not None and np.any(zero_distance_mask):
                    gradient[zero_distance_mask] = -outward_normals[zero_distance_mask]
        elif self.output_mode == "squared_distance":
            gradient[active] = 2.0 * residual_vector[active]
            if self.sdf:
                gradient[active] *= sign[active, None]
        elif self.output_mode == "regularized_distance":
            denom = np.sqrt(raw_dist2[active] + self.regularization_epsilon**2)
            gradient[active] = residual_vector[active] / denom[:, None]
            if self.sdf:
                gradient[active] *= sign[active, None]
        else:  # pragma: no cover
            raise RuntimeError(f"Unsupported output mode {self.output_mode!r}.")

        return gradient

    def _compute_output_hessian_wrt_residual(
        self,
        residual_vector: np.ndarray,
        raw_distance: np.ndarray,
        raw_dist2: np.ndarray,
        zero_distance_mask: np.ndarray,
        sign: np.ndarray,
    ) -> np.ndarray:
        hessian = np.zeros(
            (residual_vector.shape[0], self.physical_dimension, self.physical_dimension),
            dtype=float,
        )
        active = ~zero_distance_mask
        eye = np.eye(self.physical_dimension, dtype=float)

        if self.output_mode == "distance":
            safe = active & (raw_distance > self.distance_eps)
            if np.any(safe):
                rr = residual_vector[safe]
                denom = raw_distance[safe]
                outer = rr[:, :, None] * rr[:, None, :]
                hessian[safe] = (
                    eye[None, :, :] / denom[:, None, None]
                    - outer / (denom[:, None, None] ** 3)
                )
                if self.sdf:
                    hessian[safe] *= sign[safe, None, None]
        elif self.output_mode == "squared_distance":
            if np.any(active):
                scale = sign[active] if self.sdf else np.ones(np.sum(active), dtype=float)
                hessian[active] = 2.0 * scale[:, None, None] * eye[None, :, :]
        elif self.output_mode == "regularized_distance":
            if np.any(active):
                rr = residual_vector[active]
                denom = np.sqrt(raw_dist2[active] + self.regularization_epsilon**2)
                outer = rr[:, :, None] * rr[:, None, :]
                hessian[active] = (
                    eye[None, :, :] / denom[:, None, None]
                    - outer / (denom[:, None, None] ** 3)
                )
                if self.sdf:
                    hessian[active] *= sign[active, None, None]
        else:  # pragma: no cover
            raise RuntimeError(f"Unsupported output mode {self.output_mode!r}.")

        return hessian

    def _compute_free_mask(
        self,
        uv: np.ndarray,
        residual: np.ndarray,
        kind_batch: Sequence[str],
    ) -> np.ndarray:
        free_mask = np.ones_like(residual, dtype=bool)
        for local_index, kind in enumerate(kind_batch):
            fixed_axis = _parse_fixed_axis(kind)
            if fixed_axis is not None:
                free_mask[local_index, fixed_axis] = False
            if _is_point_candidate(kind):
                free_mask[local_index, :] = False

        lower = uv <= self.params.bound_eps
        upper = uv >= (1.0 - self.params.bound_eps)
        block_lower = lower & (residual > 0.0)
        block_upper = upper & (residual < 0.0)
        zero_res = np.abs(residual) <= self.params.zero_residual_tol
        free_mask &= ~(block_lower | block_upper | zero_res)
        return free_mask

    def _compute_patch_projection_data(
        self,
        info: PatchInfo,
        coeffs: np.ndarray,
        uv: np.ndarray,
        point_batch: np.ndarray,
        kind_batch: Sequence[str],
        zero_distance_mask: np.ndarray,
        sign: np.ndarray,
        reference_normals: np.ndarray,
        *,
        include_third_order: bool = False,
    ) -> Dict[str, np.ndarray]:
        cols_0, w_0, _ = compute_basis_stencil_numpy(
            uv,
            info.degrees,
            info.knot_vectors,
            cache=info.space_cache,
        )
        cols_u, w_u, _ = compute_basis_stencil_numpy(
            uv,
            info.degrees,
            info.knot_vectors,
            der_orders=(1, 0),
            cache=info.space_cache,
        )
        cols_v, w_v, _ = compute_basis_stencil_numpy(
            uv,
            info.degrees,
            info.knot_vectors,
            der_orders=(0, 1),
            cache=info.space_cache,
        )
        cols_uu, w_uu, _ = compute_basis_stencil_numpy(
            uv,
            info.degrees,
            info.knot_vectors,
            der_orders=(2, 0),
            cache=info.space_cache,
        )
        cols_uv, w_uv, _ = compute_basis_stencil_numpy(
            uv,
            info.degrees,
            info.knot_vectors,
            der_orders=(1, 1),
            cache=info.space_cache,
        )
        cols_vv, w_vv, _ = compute_basis_stencil_numpy(
            uv,
            info.degrees,
            info.knot_vectors,
            der_orders=(0, 2),
            cache=info.space_cache,
        )

        data: Dict[str, np.ndarray] = {
            "cols_0": cols_0,
            "w_0": w_0,
            "cols_u": cols_u,
            "w_u": w_u,
            "cols_v": cols_v,
            "w_v": w_v,
            "cols_uu": cols_uu,
            "w_uu": w_uu,
            "cols_uv": cols_uv,
            "w_uv": w_uv,
            "cols_vv": cols_vv,
            "w_vv": w_vv,
        }

        if include_third_order:
            cols_uuu, w_uuu, _ = compute_basis_stencil_numpy(
                uv,
                info.degrees,
                info.knot_vectors,
                der_orders=(3, 0),
                cache=info.space_cache,
            )
            cols_uuv, w_uuv, _ = compute_basis_stencil_numpy(
                uv,
                info.degrees,
                info.knot_vectors,
                der_orders=(2, 1),
                cache=info.space_cache,
            )
            cols_uvv, w_uvv, _ = compute_basis_stencil_numpy(
                uv,
                info.degrees,
                info.knot_vectors,
                der_orders=(1, 2),
                cache=info.space_cache,
            )
            cols_vvv, w_vvv, _ = compute_basis_stencil_numpy(
                uv,
                info.degrees,
                info.knot_vectors,
                der_orders=(0, 3),
                cache=info.space_cache,
            )
            data.update(
                {
                    "cols_uuu": cols_uuu,
                    "w_uuu": w_uuu,
                    "cols_uuv": cols_uuv,
                    "w_uuv": w_uuv,
                    "cols_uvv": cols_uvv,
                    "w_uvv": w_uvv,
                    "cols_vvv": cols_vvv,
                    "w_vvv": w_vvv,
                }
            )

        S = apply_basis_stencil_numpy(cols_0, w_0, coeffs)
        Su = apply_basis_stencil_numpy(cols_u, w_u, coeffs)
        Sv = apply_basis_stencil_numpy(cols_v, w_v, coeffs)
        Suu = apply_basis_stencil_numpy(cols_uu, w_uu, coeffs)
        Suv = apply_basis_stencil_numpy(cols_uv, w_uv, coeffs)
        Svv = apply_basis_stencil_numpy(cols_vv, w_vv, coeffs)

        data.update(
            {
                "S": S,
                "Su": Su,
                "Sv": Sv,
                "Suu": Suu,
                "Suv": Suv,
                "Svv": Svv,
            }
        )

        if include_third_order:
            data.update(
                {
                    "Suuu": apply_basis_stencil_numpy(data["cols_uuu"], data["w_uuu"], coeffs),
                    "Suuv": apply_basis_stencil_numpy(data["cols_uuv"], data["w_uuv"], coeffs),
                    "Suvv": apply_basis_stencil_numpy(data["cols_uvv"], data["w_uvv"], coeffs),
                    "Svvv": apply_basis_stencil_numpy(data["cols_vvv"], data["w_vvv"], coeffs),
                }
            )

        residual_vector = S - point_batch
        raw_dist2 = np.maximum(np.einsum("ij,ij->i", residual_vector, residual_vector), 0.0)
        raw_distance = np.sqrt(raw_dist2)
        outward_normals = None
        if self.sdf and self.output_mode == "distance":
            outward_normals = self._compute_oriented_surface_normals(
                Su,
                Sv,
                reference_normals,
            )

        output_gradient = self._compute_output_gradient_wrt_residual(
            residual_vector,
            raw_distance,
            raw_dist2,
            zero_distance_mask,
            sign,
            outward_normals=outward_normals,
        )
        output_hessian = self._compute_output_hessian_wrt_residual(
            residual_vector,
            raw_distance,
            raw_dist2,
            zero_distance_mask,
            sign,
        )

        residual = np.empty((point_batch.shape[0], 2), dtype=float)
        residual[:, 0] = np.einsum("ij,ij->i", residual_vector, Su)
        residual[:, 1] = np.einsum("ij,ij->i", residual_vector, Sv)

        jacobian = np.empty((point_batch.shape[0], 2, 2), dtype=float)
        jacobian[:, 0, 0] = np.einsum("ij,ij->i", Su, Su) + np.einsum("ij,ij->i", residual_vector, Suu)
        jacobian[:, 0, 1] = np.einsum("ij,ij->i", Su, Sv) + np.einsum("ij,ij->i", residual_vector, Suv)
        jacobian[:, 1, 0] = jacobian[:, 0, 1]
        jacobian[:, 1, 1] = np.einsum("ij,ij->i", Sv, Sv) + np.einsum("ij,ij->i", residual_vector, Svv)

        free_mask = self._compute_free_mask(uv, residual, kind_batch)
        dfdz = np.empty_like(residual)
        dfdz[:, 0] = np.einsum("ij,ij->i", output_gradient, Su)
        dfdz[:, 1] = np.einsum("ij,ij->i", output_gradient, Sv)
        lambda_vec = _solve_reduced_linear_system(
            jacobian,
            dfdz * free_mask,
            free_mask,
            diag_eps=self.params.diag_eps,
            det_eps=self.params.det_eps,
        )

        data.update(
            {
                "residual_vector": residual_vector,
                "raw_dist2": raw_dist2,
                "raw_distance": raw_distance,
                "output_gradient": output_gradient,
                "output_hessian": output_hessian,
                "residual": residual,
                "jacobian": jacobian,
                "free_mask": free_mask,
                "dfdz": dfdz,
                "lambda_vec": lambda_vec,
            }
        )
        return data

    def _build_sdf_surface(self, mesh: pv.PolyData) -> pv.PolyData:
        surface = mesh.clean(
            point_merging=True,
            tolerance=self.sdf_clean_tolerance,
            absolute=False,
        ).triangulate()
        return surface.compute_normals(
            cell_normals=True,
            point_normals=True,
            split_vertices=False,
            consistent_normals=True,
            auto_orient_normals=True,
            inplace=False,
        )

    def _compute_sdf_metadata(
        self,
        mesh: pv.PolyData,
        points: np.ndarray,
        projected_points: np.ndarray,
        zero_distance_mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        sdf_surface = self._build_sdf_surface(mesh)
        cloud = pv.PolyData(points)
        enclosed = cloud.select_enclosed_points(
            sdf_surface,
            tolerance=self.sdf_enclosed_tolerance,
            inside_out=False,
            check_surface=False,
        )
        inside_mask = np.asarray(enclosed["SelectedPoints"], dtype=bool)
        sign = np.where(inside_mask & ~zero_distance_mask, -1.0, 1.0)

        closest_cells = np.asarray(sdf_surface.find_closest_cell(projected_points), dtype=np.int64)
        reference_normals = np.asarray(sdf_surface.cell_data["Normals"], dtype=float)[closest_cells]
        return sign, inside_mask, reference_normals

    def _compute_oriented_surface_normals(
        self,
        Su: np.ndarray,
        Sv: np.ndarray,
        reference_normals: np.ndarray,
    ) -> np.ndarray:
        normals = np.cross(Su, Sv)
        norm = np.linalg.norm(normals, axis=1)
        safe = norm > self.degenerate_normal_tol
        normals[safe] /= norm[safe, None]

        ref = np.asarray(reference_normals, dtype=float).copy()
        ref_norm = np.linalg.norm(ref, axis=1)
        ref_safe = ref_norm > self.degenerate_normal_tol
        ref[ref_safe] /= ref_norm[ref_safe, None]
        normals[~safe] = ref[~safe]

        flip = safe & (np.einsum("ij,ij->i", normals, ref) < 0.0)
        normals[flip] *= -1.0
        return normals

    def build_degenerate_edge_map(self, mesh: pv.PolyData) -> Dict[Tuple[int, str], float]:
        mesh_points = np.asarray(mesh.points, dtype=float)
        diag = float(np.linalg.norm(mesh_points.max(axis=0) - mesh_points.min(axis=0)))
        tol = max(self.degenerate_edge_length_atol, self.degenerate_edge_length_rtol * diag)

        degenerate_edge_map: Dict[Tuple[int, str], float] = {}
        for patch_id, info in self.patch_infos.items():
            for edge_name, edge_vertex_indices in info.edge_vertex_indices.items():
                edge_xyz = mesh_points[edge_vertex_indices]
                edge_length = float(np.sum(np.linalg.norm(np.diff(edge_xyz, axis=0), axis=1)))
                if edge_length <= tol:
                    degenerate_edge_map[(int(patch_id), edge_name)] = edge_length
        return degenerate_edge_map

    def build_mesh(self, stacked_coefficients: np.ndarray) -> pv.PolyData:
        points = np.zeros((self.mesh_patch_id.shape[0], self.physical_dimension), dtype=float)

        for patch_id in self.patch_ids:
            info = self.patch_infos[int(patch_id)]
            coeffs = np.asarray(stacked_coefficients[info.start:info.stop], dtype=float).reshape(info.coefficient_shape)
            points[info.mesh_vertex_indices] = apply_basis_stencil_numpy(
                info.mesh_cols,
                info.mesh_weights,
                coeffs,
            )

        mesh = pv.PolyData(points, self.mesh_faces)
        mesh.point_data["patch_id"] = self.mesh_patch_id
        mesh.point_data["u"] = self.mesh_u
        mesh.point_data["v"] = self.mesh_v
        return mesh

    def project(self, stacked_coefficients: np.ndarray, points: np.ndarray):
        stacked_coefficients = np.asarray(stacked_coefficients, dtype=float)
        points = np.asarray(points, dtype=float).reshape(-1, self.physical_dimension)

        self.function_set_wrapper.update_coefficients(stacked_coefficients)
        mesh = self.build_mesh(stacked_coefficients)
        degenerate_edge_map = self.build_degenerate_edge_map(mesh)

        result = project_points_with_warm_start_candidates_numpy(
            function_set=self.function_set_wrapper,
            points=points,
            patch_indices=self.patch_ids,
            mesh=mesh,
            edge_map=self.edge_map,
            degenerate_edge_map=degenerate_edge_map,
            eps_edge=self.eps_edge,
            include_current_patch_boundary=self.include_current_patch_boundary,
            include_neighbor_patch=self.include_neighbor_patch,
            include_neighbor_boundary=self.include_neighbor_boundary,
            retry_on_failure=self.retry_on_failure,
            retry_num_closest_edges=self.retry_num_closest_edges,
            params=self.params,
        )
        raw_dist2 = np.maximum(result.dist2, 0.0)
        raw_distance = np.sqrt(raw_dist2)
        zero_distance_mask = raw_distance <= self.distance_eps
        sign = np.ones_like(raw_distance)
        inside_mask = np.zeros_like(zero_distance_mask)
        reference_normals = np.zeros((points.shape[0], self.physical_dimension), dtype=float)
        if self.sdf:
            sign, inside_mask, reference_normals = self._compute_sdf_metadata(
                mesh,
                points,
                np.asarray(result.projected_points, dtype=float),
                zero_distance_mask,
            )
        output_measure = self._compute_output_measure(
            raw_distance,
            raw_dist2,
            zero_distance_mask,
            sign,
        )

        if self.debug:
            # print debug info
            # number of converged points
            num_converged = np.sum(result.converged)
            # number of non-converged points
            num_non_converged = len(points) - num_converged
            # max residual of all points
            num_points = len(points)
            max_residual = np.max(np.linalg.norm(result.residual.reshape(num_points, -1), axis=1))
            # max number of iterations taken by any point
            max_iterations = np.max(result.iterations)

            print("Debug info for forward pass:")
            print("    Num converged:", num_converged)
            print("    Num non-converged:", num_non_converged)
            print("    Max residual:", max_residual)
            print("    Max iterations:", max_iterations)

        state = {
            "patch_id": np.asarray(result.patch_id, dtype=int),
            "uv": np.asarray(result.uv, dtype=float),
            "candidate_kind": list(result.candidate_kind),
            "converged": np.asarray(result.converged, dtype=bool),
            "iterations": np.asarray(result.iterations, dtype=int),
            "projected_points": np.asarray(result.projected_points, dtype=float),
            "distance": raw_distance,
            "raw_dist2": raw_dist2,
            "output_measure": output_measure,
            "zero_distance_mask": zero_distance_mask,
            "sign": sign,
            "inside_mask": inside_mask,
            "reference_normals": reference_normals,
            "residual": np.asarray(result.residual, dtype=float),
            "degenerate_edge_map": degenerate_edge_map,
        }
        return output_measure, state

    def compute_vjp(
        self,
        stacked_coefficients: np.ndarray,
        points: np.ndarray,
        d_distances: np.ndarray,
        forward_state: Dict[str, object],
    ) -> tuple[np.ndarray, np.ndarray]:
        stacked_coefficients = np.asarray(stacked_coefficients, dtype=float)
        points = np.asarray(points, dtype=float).reshape(-1, self.physical_dimension)
        d_distances = np.asarray(d_distances, dtype=float).reshape(-1)

        d_points = np.zeros_like(points)
        d_coefficients = np.zeros_like(stacked_coefficients)

        if not np.any(d_distances):
            return d_points, d_coefficients

        selected_patch_id = np.asarray(forward_state["patch_id"], dtype=int)
        selected_uv = np.asarray(forward_state["uv"], dtype=float)
        candidate_kind = list(forward_state["candidate_kind"])
        zero_distance_mask = np.asarray(
            forward_state.get("zero_distance_mask", np.zeros(points.shape[0], dtype=bool)),
            dtype=bool,
        )
        sign = np.asarray(
            forward_state.get("sign", np.ones(points.shape[0], dtype=float)),
            dtype=float,
        )
        reference_normals = np.asarray(
            forward_state.get(
                "reference_normals",
                np.zeros((points.shape[0], self.physical_dimension), dtype=float),
            ),
            dtype=float,
        )

        for patch_id in self.patch_ids:
            point_indices = np.where(selected_patch_id == int(patch_id))[0]
            if point_indices.size == 0:
                continue

            info = self.patch_infos[int(patch_id)]
            coeffs = np.asarray(stacked_coefficients[info.start:info.stop], dtype=float).reshape(info.coefficient_shape)

            uv = selected_uv[point_indices]
            point_batch = points[point_indices]
            cotangent_batch = d_distances[point_indices]
            kind_batch = [candidate_kind[idx] for idx in point_indices]

            data = self._compute_patch_projection_data(
                info,
                coeffs,
                uv,
                point_batch,
                kind_batch,
                zero_distance_mask[point_indices],
                sign[point_indices],
                reference_normals[point_indices],
            )

            cols_0 = data["cols_0"]
            w_0 = data["w_0"]
            cols_u = data["cols_u"]
            w_u = data["w_u"]
            cols_v = data["cols_v"]
            w_v = data["w_v"]
            Su = data["Su"]
            Sv = data["Sv"]
            residual_vector = data["residual_vector"]
            output_gradient = data["output_gradient"]
            lambda_vec = data["lambda_vec"]

            d_points[point_indices] = cotangent_batch[:, None] * (
                -output_gradient + lambda_vec[:, 0, None] * Su + lambda_vec[:, 1, None] * Sv
            )

            local_grad = np.zeros((info.stop - info.start, self.physical_dimension), dtype=float)

            primary_term = cotangent_batch[:, None] * (
                output_gradient - lambda_vec[:, 0, None] * Su - lambda_vec[:, 1, None] * Sv
            )
            np.add.at(
                local_grad,
                cols_0.ravel(),
                (w_0[:, :, None] * primary_term[:, None, :]).reshape(-1, self.physical_dimension),
            )

            if np.any(lambda_vec[:, 0]):
                u_term = (
                    -cotangent_batch[:, None, None]
                    * lambda_vec[:, 0, None, None]
                    * w_u[:, :, None]
                    * residual_vector[:, None, :]
                )
                np.add.at(local_grad, cols_u.ravel(), u_term.reshape(-1, self.physical_dimension))

            if np.any(lambda_vec[:, 1]):
                v_term = (
                    -cotangent_batch[:, None, None]
                    * lambda_vec[:, 1, None, None]
                    * w_v[:, :, None]
                    * residual_vector[:, None, :]
                )
                np.add.at(local_grad, cols_v.ravel(), v_term.reshape(-1, self.physical_dimension))

            d_coefficients[info.start:info.stop] += local_grad

        return d_points, d_coefficients

    def compute_vjp_vjp(
        self,
        stacked_coefficients: np.ndarray,
        points: np.ndarray,
        d_distances: np.ndarray,
        d_points_cotangent: np.ndarray,
        d_coefficients_cotangent: np.ndarray,
        forward_state: Dict[str, object],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        stacked_coefficients = np.asarray(stacked_coefficients, dtype=float)
        points = np.asarray(points, dtype=float).reshape(-1, self.physical_dimension)
        d_distances = np.asarray(d_distances, dtype=float).reshape(-1)
        d_points_cotangent = np.asarray(d_points_cotangent, dtype=float).reshape(-1, self.physical_dimension)
        d_coefficients_cotangent = np.asarray(d_coefficients_cotangent, dtype=float)

        dd_points = np.zeros_like(points)
        dd_coefficients = np.zeros_like(stacked_coefficients)
        dd_d_distances = np.zeros_like(d_distances)

        if (not np.any(d_distances)) or (
            (not np.any(d_points_cotangent)) and (not np.any(d_coefficients_cotangent))
        ):
            return dd_points, dd_coefficients, dd_d_distances

        selected_patch_id = np.asarray(forward_state["patch_id"], dtype=int)
        selected_uv = np.asarray(forward_state["uv"], dtype=float)
        candidate_kind = list(forward_state["candidate_kind"])
        zero_distance_mask = np.asarray(
            forward_state.get("zero_distance_mask", np.zeros(points.shape[0], dtype=bool)),
            dtype=bool,
        )
        sign = np.asarray(
            forward_state.get("sign", np.ones(points.shape[0], dtype=float)),
            dtype=float,
        )
        reference_normals = np.asarray(
            forward_state.get(
                "reference_normals",
                np.zeros((points.shape[0], self.physical_dimension), dtype=float),
            ),
            dtype=float,
        )

        for patch_id in self.patch_ids:
            point_indices = np.where(selected_patch_id == int(patch_id))[0]
            if point_indices.size == 0:
                continue

            info = self.patch_infos[int(patch_id)]
            coeffs = np.asarray(stacked_coefficients[info.start:info.stop], dtype=float).reshape(info.coefficient_shape)
            direction_coeffs = np.asarray(
                d_coefficients_cotangent[info.start:info.stop],
                dtype=float,
            ).reshape(info.coefficient_shape)

            uv = selected_uv[point_indices]
            point_batch = points[point_indices]
            point_direction = d_points_cotangent[point_indices]
            cotangent_batch = d_distances[point_indices]
            kind_batch = [candidate_kind[idx] for idx in point_indices]

            data = self._compute_patch_projection_data(
                info,
                coeffs,
                uv,
                point_batch,
                kind_batch,
                zero_distance_mask[point_indices],
                sign[point_indices],
                reference_normals[point_indices],
                include_third_order=True,
            )

            cols_0 = data["cols_0"]
            w_0 = data["w_0"]
            cols_u = data["cols_u"]
            w_u = data["w_u"]
            cols_v = data["cols_v"]
            w_v = data["w_v"]
            w_uu = data["w_uu"]
            w_uv = data["w_uv"]
            w_vv = data["w_vv"]

            residual_vector = data["residual_vector"]
            output_gradient = data["output_gradient"]
            output_hessian = data["output_hessian"]
            jacobian = data["jacobian"]
            free_mask = data["free_mask"]
            lambda_vec = data["lambda_vec"]

            Su = data["Su"]
            Sv = data["Sv"]
            Suu = data["Suu"]
            Suv = data["Suv"]
            Svv = data["Svv"]
            Suuu = data["Suuu"]
            Suuv = data["Suuv"]
            Suvv = data["Suvv"]
            Svvv = data["Svvv"]

            direct_S = apply_basis_stencil_numpy(cols_0, w_0, direction_coeffs)
            direct_Su = apply_basis_stencil_numpy(cols_u, w_u, direction_coeffs)
            direct_Sv = apply_basis_stencil_numpy(cols_v, w_v, direction_coeffs)
            direct_Suu = apply_basis_stencil_numpy(data["cols_uu"], w_uu, direction_coeffs)
            direct_Suv = apply_basis_stencil_numpy(data["cols_uv"], w_uv, direction_coeffs)
            direct_Svv = apply_basis_stencil_numpy(data["cols_vv"], w_vv, direction_coeffs)

            direct_residual_vector = direct_S - point_direction
            direct_state_rhs = np.empty((point_indices.size, 2), dtype=float)
            direct_state_rhs[:, 0] = -(
                np.einsum("ij,ij->i", direct_residual_vector, Su)
                + np.einsum("ij,ij->i", residual_vector, direct_Su)
            )
            direct_state_rhs[:, 1] = -(
                np.einsum("ij,ij->i", direct_residual_vector, Sv)
                + np.einsum("ij,ij->i", residual_vector, direct_Sv)
            )
            delta_uv = _solve_reduced_linear_system(
                jacobian,
                direct_state_rhs,
                free_mask,
                diag_eps=self.params.diag_eps,
                det_eps=self.params.det_eps,
            )

            delta_S = direct_S + delta_uv[:, 0, None] * Su + delta_uv[:, 1, None] * Sv
            delta_Su = direct_Su + delta_uv[:, 0, None] * Suu + delta_uv[:, 1, None] * Suv
            delta_Sv = direct_Sv + delta_uv[:, 0, None] * Suv + delta_uv[:, 1, None] * Svv
            delta_Suu = direct_Suu + delta_uv[:, 0, None] * Suuu + delta_uv[:, 1, None] * Suuv
            delta_Suv = direct_Suv + delta_uv[:, 0, None] * Suuv + delta_uv[:, 1, None] * Suvv
            delta_Svv = direct_Svv + delta_uv[:, 0, None] * Suvv + delta_uv[:, 1, None] * Svvv
            delta_residual_vector = delta_S - point_direction

            delta_output_gradient = np.einsum("ijk,ik->ij", output_hessian, delta_residual_vector)
            delta_dfdz = np.empty((point_indices.size, 2), dtype=float)
            delta_dfdz[:, 0] = np.einsum("ij,ij->i", delta_output_gradient, Su) + np.einsum(
                "ij,ij->i",
                output_gradient,
                delta_Su,
            )
            delta_dfdz[:, 1] = np.einsum("ij,ij->i", delta_output_gradient, Sv) + np.einsum(
                "ij,ij->i",
                output_gradient,
                delta_Sv,
            )

            delta_jacobian = np.empty((point_indices.size, 2, 2), dtype=float)
            delta_jacobian[:, 0, 0] = (
                2.0 * np.einsum("ij,ij->i", Su, delta_Su)
                + np.einsum("ij,ij->i", delta_residual_vector, Suu)
                + np.einsum("ij,ij->i", residual_vector, delta_Suu)
            )
            delta_jacobian[:, 0, 1] = (
                np.einsum("ij,ij->i", delta_Su, Sv)
                + np.einsum("ij,ij->i", Su, delta_Sv)
                + np.einsum("ij,ij->i", delta_residual_vector, Suv)
                + np.einsum("ij,ij->i", residual_vector, delta_Suv)
            )
            delta_jacobian[:, 1, 0] = delta_jacobian[:, 0, 1]
            delta_jacobian[:, 1, 1] = (
                2.0 * np.einsum("ij,ij->i", Sv, delta_Sv)
                + np.einsum("ij,ij->i", delta_residual_vector, Svv)
                + np.einsum("ij,ij->i", residual_vector, delta_Svv)
            )

            delta_lambda_rhs = (delta_dfdz - np.einsum("ijk,ik->ij", delta_jacobian, lambda_vec)) * free_mask
            delta_lambda = _solve_reduced_linear_system(
                jacobian,
                delta_lambda_rhs,
                free_mask,
                diag_eps=self.params.diag_eps,
                det_eps=self.params.det_eps,
            )

            dd_points[point_indices] = cotangent_batch[:, None] * (
                -delta_output_gradient
                + delta_lambda[:, 0, None] * Su
                + lambda_vec[:, 0, None] * delta_Su
                + delta_lambda[:, 1, None] * Sv
                + lambda_vec[:, 1, None] * delta_Sv
            )

            local_hvp = np.zeros((info.stop - info.start, self.physical_dimension), dtype=float)

            base_alpha = (
                output_gradient
                - lambda_vec[:, 0, None] * Su
                - lambda_vec[:, 1, None] * Sv
            )
            delta_alpha = (
                delta_output_gradient
                - delta_lambda[:, 0, None] * Su
                - lambda_vec[:, 0, None] * delta_Su
                - delta_lambda[:, 1, None] * Sv
                - lambda_vec[:, 1, None] * delta_Sv
            )
            delta_w0 = delta_uv[:, 0, None] * w_u + delta_uv[:, 1, None] * w_v
            term0 = cotangent_batch[:, None, None] * (
                w_0[:, :, None] * delta_alpha[:, None, :]
                + delta_w0[:, :, None] * base_alpha[:, None, :]
            )
            np.add.at(local_hvp, cols_0.ravel(), term0.reshape(-1, self.physical_dimension))

            beta_u = lambda_vec[:, 0, None] * residual_vector
            delta_beta_u = delta_lambda[:, 0, None] * residual_vector + lambda_vec[:, 0, None] * delta_residual_vector
            delta_wu = delta_uv[:, 0, None] * w_uu + delta_uv[:, 1, None] * w_uv
            term_u = -cotangent_batch[:, None, None] * (
                w_u[:, :, None] * delta_beta_u[:, None, :]
                + delta_wu[:, :, None] * beta_u[:, None, :]
            )
            np.add.at(local_hvp, cols_u.ravel(), term_u.reshape(-1, self.physical_dimension))

            beta_v = lambda_vec[:, 1, None] * residual_vector
            delta_beta_v = delta_lambda[:, 1, None] * residual_vector + lambda_vec[:, 1, None] * delta_residual_vector
            delta_wv = delta_uv[:, 0, None] * w_uv + delta_uv[:, 1, None] * w_vv
            term_v = -cotangent_batch[:, None, None] * (
                w_v[:, :, None] * delta_beta_v[:, None, :]
                + delta_wv[:, :, None] * beta_v[:, None, :]
            )
            np.add.at(local_hvp, cols_v.ravel(), term_v.reshape(-1, self.physical_dimension))

            dd_coefficients[info.start:info.stop] += local_hvp
            dd_d_distances[point_indices] = np.einsum("ij,ij->i", output_gradient, delta_residual_vector)

        return dd_points, dd_coefficients, dd_d_distances


class FunctionSetClosestDistanceVJP(csdl.experimental.CustomExplicitOperationBeta):
    def __init__(self, model: FunctionSetProjectionModel, shared_state: Dict[str, object]):
        super().__init__()
        self.model = model
        self.shared_state = shared_state

    def evaluate(self, inputs, d_outputs):
        coefficients = inputs["coefficients"]
        points = inputs["points"].reshape(-1, self.model.physical_dimension)
        d_closest_distance = d_outputs["closest_distance"].reshape(-1)

        self.declare_input("coefficients", coefficients)
        self.declare_input("points", points)
        self.declare_input("d_closest_distance", d_closest_distance)

        d_coefficients = self.create_output("d_coefficients", coefficients.shape)
        d_points = self.create_output("d_points", points.shape)

        self.declare_vjp_function(
            FunctionSetClosestDistanceVJPVJP,
            model=self.model,
            shared_state=self.shared_state,
        )

        return {
            "coefficients": d_coefficients,
            "points": d_points,
        }

    def compute(self, inputs, outputs):
        if "forward" not in self.shared_state:
            raise RuntimeError("Forward projection state is unavailable for VJP evaluation.")

        coefficients = np.asarray(inputs["coefficients"], dtype=float)
        points = np.asarray(inputs["points"], dtype=float).reshape(-1, self.model.physical_dimension)
        d_closest_distance = np.asarray(inputs["d_closest_distance"], dtype=float).reshape(-1)

        d_points, d_coefficients = self.model.compute_vjp(
            coefficients,
            points,
            d_closest_distance,
            self.shared_state["forward"],
        )
        outputs["d_points"] = d_points
        outputs["d_coefficients"] = d_coefficients


class FunctionSetClosestDistanceVJPVJP(csdl.experimental.CustomExplicitOperationBeta):
    def __init__(self, model: FunctionSetProjectionModel, shared_state: Dict[str, object]):
        super().__init__()
        self.model = model
        self.shared_state = shared_state

    def evaluate(self, inputs, d_outputs):
        coefficients = inputs["coefficients"]
        points = inputs["points"].reshape(-1, self.model.physical_dimension)
        d_closest_distance = inputs["d_closest_distance"].reshape(-1)
        d_d_coefficients = d_outputs["d_coefficients"]
        d_d_points = d_outputs["d_points"].reshape(-1, self.model.physical_dimension)

        self.declare_input("coefficients", coefficients)
        self.declare_input("points", points)
        self.declare_input("d_closest_distance", d_closest_distance)
        self.declare_input("d_d_coefficients", d_d_coefficients)
        self.declare_input("d_d_points", d_d_points)

        dd_coefficients = self.create_output("dd_coefficients", coefficients.shape)
        dd_points = self.create_output("dd_points", points.shape)
        dd_d_closest_distance = self.create_output("dd_d_closest_distance", d_closest_distance.shape)

        return {
            "coefficients": dd_coefficients,
            "points": dd_points,
            "d_closest_distance": dd_d_closest_distance,
        }

    def compute(self, inputs, outputs):
        if "forward" not in self.shared_state:
            raise RuntimeError("Forward projection state is unavailable for second-order VJP evaluation.")

        coefficients = np.asarray(inputs["coefficients"], dtype=float)
        points = np.asarray(inputs["points"], dtype=float).reshape(-1, self.model.physical_dimension)
        d_closest_distance = np.asarray(inputs["d_closest_distance"], dtype=float).reshape(-1)
        d_d_coefficients = np.asarray(inputs["d_d_coefficients"], dtype=float)
        d_d_points = np.asarray(inputs["d_d_points"], dtype=float).reshape(-1, self.model.physical_dimension)

        dd_points, dd_coefficients, dd_d_closest_distance = self.model.compute_vjp_vjp(
            coefficients,
            points,
            d_closest_distance,
            d_d_points,
            d_d_coefficients,
            self.shared_state["forward"],
        )
        outputs["dd_points"] = dd_points
        outputs["dd_coefficients"] = dd_coefficients
        outputs["dd_d_closest_distance"] = dd_d_closest_distance


class FunctionSetClosestDistanceOperation(csdl.experimental.CustomExplicitOperationBeta):
    def __init__(self, model: FunctionSetProjectionModel):
        super().__init__()
        self.model = model
        self.shared_state: Dict[str, object] = {}

    def evaluate(self, coefficients, points):
        points = points.reshape(-1, self.model.physical_dimension)

        self.declare_input("coefficients", coefficients)
        self.declare_input("points", points)

        closest_distance = self.create_output("closest_distance", (points.shape[0],))

        self.declare_vjp_function(
            FunctionSetClosestDistanceVJP,
            model=self.model,
            shared_state=self.shared_state,
        )

        return closest_distance

    def compute(self, inputs, outputs):
        coefficients = np.asarray(inputs["coefficients"], dtype=float)
        points = np.asarray(inputs["points"], dtype=float).reshape(-1, self.model.physical_dimension)

        closest_distance, forward_state = self.model.project(coefficients, points)
        self.shared_state["forward"] = forward_state
        outputs["closest_distance"] = closest_distance


def _build_demo_function_set():
    import lsdo_function_spaces as lfs

    degree = (3, 3)
    coefficients_shape = (4, 4)
    knots = (
        np.concatenate([np.zeros(degree[0]), np.linspace(0.0, 1.0, coefficients_shape[0] - degree[0] + 1), np.ones(degree[0])]),
        np.concatenate([np.zeros(degree[1]), np.linspace(0.0, 1.0, coefficients_shape[1] - degree[1] + 1), np.ones(degree[1])]),
    )

    y_coords = np.linspace(0.0, 1.0, coefficients_shape[1])
    x_patch_0 = np.linspace(0.0, 1.0, coefficients_shape[0])
    x_patch_1 = np.linspace(1.0, 2.0, coefficients_shape[0])

    X0, Y0 = np.meshgrid(x_patch_0, y_coords, indexing="ij")
    X1, Y1 = np.meshgrid(x_patch_1, y_coords, indexing="ij")

    Z0 = 0.08 * np.sin(np.pi * X0 / 2.0) * np.cos(np.pi * Y0)
    Z1 = 0.08 * np.sin(np.pi * X1 / 2.0) * np.cos(np.pi * Y1)

    coeffs_0 = np.stack([X0, Y0, Z0], axis=-1)
    coeffs_1 = np.stack([X1, Y1, Z1], axis=-1)
    coeffs_1[0, :, :] = coeffs_0[-1, :, :]

    space_0 = lfs.BSplineSpaceNew(
        num_parametric_dimensions=2,
        degree=degree,
        coefficients_shape=coefficients_shape,
        knots=knots,
    )
    space_1 = lfs.BSplineSpaceNew(
        num_parametric_dimensions=2,
        degree=degree,
        coefficients_shape=coefficients_shape,
        knots=knots,
    )

    return lfs.FunctionSet(
        functions={
            0: lfs.Function(space=space_0, coefficients=coeffs_0),
            1: lfs.Function(space=space_1, coefficients=coeffs_1),
        }
    )


if __name__ == "__main__":
    np.random.seed(7)

    setup_recorder = csdl.Recorder(inline=True)
    setup_recorder.start()

    function_set = _build_demo_function_set()
    seam_model = FunctionSetProjectionModel(
        function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        params=OrthogonalityNewtonParams(max_iter=30, tol_res=1e-12, tol_step=1e-12),
    )

    stacked_coefficients = stack_function_set_coefficients(function_set, seam_model.patch_ids)

    seam_parametric_coordinates = [
        (0, np.array([0.995, 0.25])),
        (0, np.array([0.997, 0.75])),
        (1, np.array([0.005, 0.35])),
        (1, np.array([0.008, 0.65])),
    ]
    seam_surface_points = np.asarray(
        function_set.evaluate(parametric_coordinates=seam_parametric_coordinates, non_csdl=True),
        dtype=float,
    ).reshape(-1, 3)
    seam_query_points = seam_surface_points + np.array([0.0, 0.0, 0.12])
    seam_distances, seam_state = seam_model.project(stacked_coefficients, seam_query_points)
    print("Seam verification candidate kinds:", seam_state["candidate_kind"])
    print("Seam verification converged:", seam_state["converged"].tolist())
    print("Seam verification distances:", seam_distances)

    interior_parametric_coordinates = [
        (0, np.array([0.20, 0.25])),
        (0, np.array([0.35, 0.70])),
        (0, np.array([0.55, 0.40])),
        (0, np.array([0.70, 0.80])),
        (1, np.array([0.25, 0.20])),
        (1, np.array([0.40, 0.60])),
        (1, np.array([0.65, 0.35])),
        (1, np.array([0.80, 0.75])),
    ]
    interior_surface_points = np.asarray(
        function_set.evaluate(parametric_coordinates=interior_parametric_coordinates, non_csdl=True),
        dtype=float,
    ).reshape(-1, 3)
    contact_parametric_coordinates = [(0, np.array([0.35, 0.60]))]
    contact_surface_point = np.asarray(
        function_set.evaluate(parametric_coordinates=contact_parametric_coordinates, non_csdl=True),
        dtype=float,
    ).reshape(-1, 3)
    query_points = interior_surface_points + np.array([0.0, 0.0, 0.15])

    def run_mode_verification(output_mode: str, regularization_epsilon: float = 1e-8) -> None:
        print("")
        print(f"Output mode: {output_mode}")

        model = FunctionSetProjectionModel(
            function_set,
            warm_start_nu=40,
            warm_start_nv=40,
            edge_map_num_samples=25,
            output_mode=output_mode,
            regularization_epsilon=regularization_epsilon,
            params=OrthogonalityNewtonParams(max_iter=30, tol_res=1e-12, tol_step=1e-12),
            debug=True,
            # sdf=True,
        )

        recorder = csdl.Recorder(inline=True)
        recorder.start()

        coefficients_csdl = csdl.Variable(name=f"{output_mode}_stacked_coefficients", value=stacked_coefficients)
        points_csdl = csdl.Variable(name=f"{output_mode}_points_to_project", value=query_points)
        coefficients_csdl.set_as_design_variable()
        points_csdl.set_as_design_variable()

        projection_op = FunctionSetClosestDistanceOperation(model=model)
        closest_measure = projection_op.evaluate(
            coefficients=coefficients_csdl,
            points=points_csdl,
        )
        first_derivative = csdl.derivative(closest_measure, points_csdl)
        objective = csdl.sum(first_derivative)
        objective.name = f"{output_mode}_sum"
        objective.set_as_objective()
        recorder.stop()
        py_sim = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
        py_sim.run()
        print("Baseline output:", closest_measure.value)
        py_sim.check_optimization_derivatives(step_size=1e-7, raise_on_error=False)
        print("Forward candidate kinds:", projection_op.shared_state["forward"]["candidate_kind"])
        print("Forward converged:", projection_op.shared_state["forward"]["converged"].tolist())

        # contact_recorder = csdl.Recorder(inline=True)
        # contact_recorder.start()

        # contact_coefficients_csdl = csdl.Variable(
        #     name=f"{output_mode}_contact_stacked_coefficients",
        #     value=stacked_coefficients,
        # )
        # contact_points_csdl = csdl.Variable(
        #     name=f"{output_mode}_contact_points_to_project",
        #     value=contact_surface_point,
        # )
        # contact_projection_op = FunctionSetClosestDistanceOperation(model=model)
        # contact_measure = contact_projection_op.evaluate(
        #     coefficients=contact_coefficients_csdl,
        #     points=contact_points_csdl,
        # )
        # contact_objective = csdl.sum(contact_measure)
        # d_contact_d_points = csdl.derivative(contact_objective, contact_points_csdl)
        # d_contact_d_coeffs = csdl.derivative(contact_objective, contact_coefficients_csdl)

        # contact_sim = csdl.experimental.JaxSimulator(recorder=contact_recorder, gpu=False)
        # contact_sim.run()
        # print("Contact output:", contact_measure.value)
        # print("Contact d_output_d_points norm:", np.linalg.norm(d_contact_d_points.value))
        # print("Contact d_output_d_coeffs norm:", np.linalg.norm(d_contact_d_coeffs.value))

    run_mode_verification("distance")
    run_mode_verification("squared_distance")
    run_mode_verification("regularized_distance", regularization_epsilon=1e-6)
