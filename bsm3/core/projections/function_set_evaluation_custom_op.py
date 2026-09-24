"""Differentiable evaluation of a function set at fixed parametric coordinates.

Unlike projection, the parametric coordinates here are fixed at setup, so the
map from coefficients to points is linear and its reverse mode is the exact
transpose of a cached basis matrix.

:class:`FunctionSetEvaluationModel` holds the NumPy setup-time state;
:class:`FunctionSetEvaluationOperation` and :class:`FunctionSetEvaluationVJP`
wrap it as CSDL custom operations. Coefficients use the stacked convention:
patches concatenated by row in ascending patch-ID order.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

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

from lsdo_function_spaces.core.spaces.non_cython_bsplines.compute_basis_matrix_numpy_factory_patched import (
    apply_basis_stencil_numpy,
    compute_basis_stencil_numpy,
    make_bspline_space_cache,
)


@dataclass(frozen=True)
class EvaluationPatchInfo:
    """Cached per-patch data for evaluating at fixed parametric coordinates.

    Attributes
    ----------
    patch_id
        Identifier of the patch inside the owning function set.
    start, stop
        Half-open row range this patch occupies in the stacked coefficient array.
    """
    patch_id: int
    degrees: tuple[int, ...]
    knot_vectors: tuple[np.ndarray, ...]
    coefficient_shape: tuple[int, ...]
    start: int
    stop: int
    space_cache: object


class FunctionSetEvaluationModel:
    """Setup-time NumPy state for evaluating a function set at fixed points.

    The parametric coordinates are fixed at construction, so evaluation is linear
    in the coefficients: each output point is a cached basis row times that
    patch's control points. This class is pure NumPy; the CSDL wrappers below hold
    a reference to it.
    """
    def __init__(
        self,
        function_set,
        *,
        patch_indices: Optional[Iterable[int]] = None,
    ):
        if patch_indices is None:
            patch_indices = sorted(int(idx) for idx in function_set.functions.keys())
        else:
            patch_indices = [int(idx) for idx in patch_indices]

        self.patch_ids = tuple(patch_indices)
        self.patch_id_set = set(self.patch_ids)
        first_patch = function_set.functions[self.patch_ids[0]]
        self.physical_dimension = int(np.asarray(first_patch.coefficients.value).shape[-1])

        patch_infos: Dict[int, EvaluationPatchInfo] = {}
        start = 0
        for patch_id in self.patch_ids:
            fun = function_set.functions[int(patch_id)]
            coeffs = np.asarray(fun.coefficients.value, dtype=float)
            coeff_shape = tuple(int(v) for v in coeffs.shape)
            num_ctrl = int(np.prod(coeff_shape[:-1]))
            stop = start + num_ctrl

            degrees = tuple(int(v) for v in fun.space.degree)
            knot_vectors = tuple(np.asarray(k, dtype=float) for k in fun.space.knots)
            patch_infos[int(patch_id)] = EvaluationPatchInfo(
                patch_id=int(patch_id),
                degrees=degrees,
                knot_vectors=knot_vectors,
                coefficient_shape=coeff_shape,
                start=start,
                stop=stop,
                space_cache=make_bspline_space_cache(degrees, knot_vectors),
            )
            start = stop

        self.patch_infos = patch_infos
        self.total_num_control_points = start

    def _parse_parametric_coordinates(
        self,
        parametric_coordinates: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        parametric_coordinates = np.asarray(parametric_coordinates, dtype=float).reshape(-1, 3)
        patch_id = np.rint(parametric_coordinates[:, 0]).astype(int)
        uv = np.asarray(parametric_coordinates[:, 1:3], dtype=float)

        invalid = sorted(set(int(idx) for idx in patch_id) - self.patch_id_set)
        if invalid:
            raise ValueError(
                f"Encountered patch ids {invalid} that are not present in this evaluation model."
            )

        return patch_id, uv

    def evaluate(
        self,
        stacked_coefficients: np.ndarray,
        parametric_coordinates: np.ndarray,
    ) -> np.ndarray:
        """Evaluate the surface at the cached parametric coordinates.

        Parameters
        ----------
        stacked_coefficients
            Coefficients in the stacked convention: patches concatenated by row in
            ascending patch-ID order.

        Returns
        -------
        numpy.ndarray
            Points of shape ``(num_coordinates, physical_dimension)``.
        """
        stacked_coefficients = np.asarray(stacked_coefficients, dtype=float)
        patch_id, uv = self._parse_parametric_coordinates(parametric_coordinates)

        output = np.zeros((uv.shape[0], self.physical_dimension), dtype=float)
        for current_patch_id in self.patch_ids:
            point_indices = np.where(patch_id == int(current_patch_id))[0]
            if point_indices.size == 0:
                continue

            info = self.patch_infos[int(current_patch_id)]
            coeffs = np.asarray(stacked_coefficients[info.start:info.stop], dtype=float).reshape(info.coefficient_shape)
            cols_0, w_0, _ = compute_basis_stencil_numpy(
                uv[point_indices],
                info.degrees,
                info.knot_vectors,
                cache=info.space_cache,
            )
            output[point_indices] = apply_basis_stencil_numpy(cols_0, w_0, coeffs)

        return output

    def compute_vjp(
        self,
        stacked_coefficients: np.ndarray,
        parametric_coordinates: np.ndarray,
        d_evaluated_points: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply the reverse-mode product for one seed.

        Parameters
        ----------
        d_points
            Reverse seed with the shape of the evaluated points.

        Returns
        -------
        numpy.ndarray
            Coefficient cotangent in the stacked convention.

        Notes
        -----
        Because the parametric coordinates are fixed, this map is exactly the
        transpose of the cached basis matrix; no linearization error is involved.
        """
        stacked_coefficients = np.asarray(stacked_coefficients, dtype=float)
        d_evaluated_points = np.asarray(d_evaluated_points, dtype=float).reshape(-1, self.physical_dimension)

        d_coefficients = np.zeros_like(stacked_coefficients)
        d_parametric_coordinates = np.zeros_like(np.asarray(parametric_coordinates, dtype=float).reshape(-1, 3))

        if not np.any(d_evaluated_points):
            return d_coefficients, d_parametric_coordinates

        patch_id, uv = self._parse_parametric_coordinates(parametric_coordinates)

        for current_patch_id in self.patch_ids:
            point_indices = np.where(patch_id == int(current_patch_id))[0]
            if point_indices.size == 0:
                continue

            info = self.patch_infos[int(current_patch_id)]
            coeffs = np.asarray(stacked_coefficients[info.start:info.stop], dtype=float).reshape(info.coefficient_shape)
            uv_batch = uv[point_indices]
            cotangent_batch = d_evaluated_points[point_indices]

            cols_0, w_0, _ = compute_basis_stencil_numpy(
                uv_batch,
                info.degrees,
                info.knot_vectors,
                cache=info.space_cache,
            )
            cols_u, w_u, _ = compute_basis_stencil_numpy(
                uv_batch,
                info.degrees,
                info.knot_vectors,
                der_orders=(1, 0),
                cache=info.space_cache,
            )
            cols_v, w_v, _ = compute_basis_stencil_numpy(
                uv_batch,
                info.degrees,
                info.knot_vectors,
                der_orders=(0, 1),
                cache=info.space_cache,
            )

            Su = apply_basis_stencil_numpy(cols_u, w_u, coeffs)
            Sv = apply_basis_stencil_numpy(cols_v, w_v, coeffs)

            local_grad = np.zeros((info.stop - info.start, self.physical_dimension), dtype=float)
            np.add.at(
                local_grad,
                cols_0.ravel(),
                (w_0[:, :, None] * cotangent_batch[:, None, :]).reshape(-1, self.physical_dimension),
            )

            d_coefficients[info.start:info.stop] += local_grad
            d_parametric_coordinates[point_indices, 1] = np.einsum("ij,ij->i", cotangent_batch, Su)
            d_parametric_coordinates[point_indices, 2] = np.einsum("ij,ij->i", cotangent_batch, Sv)

        return d_coefficients, d_parametric_coordinates


class FunctionSetEvaluationVJP(csdl.experimental.CustomExplicitOperationBeta):
    """CSDL custom operation for the reverse product of evaluation."""
    def __init__(self, model: FunctionSetEvaluationModel):
        super().__init__()
        self.model = model

    def evaluate(self, inputs, d_outputs):
        """Declare the reverse seed and the coefficient cotangent output."""
        coefficients = inputs["coefficients"]
        parametric_coordinates = inputs["parametric_coordinates"].reshape(-1, 3)
        d_evaluated_points = d_outputs["evaluated_points"].reshape(-1, self.model.physical_dimension)

        self.declare_input("coefficients", coefficients)
        self.declare_input("parametric_coordinates", parametric_coordinates)
        self.declare_input("d_evaluated_points", d_evaluated_points)

        d_coefficients = self.create_output("d_coefficients", coefficients.shape)
        d_parametric_coordinates = self.create_output("d_parametric_coordinates", parametric_coordinates.shape)

        return {
            "coefficients": d_coefficients,
            "parametric_coordinates": d_parametric_coordinates,
        }

    def compute(self, inputs, outputs):
        """Evaluate the coefficient cotangent into ``outputs``."""
        coefficients = np.asarray(inputs["coefficients"], dtype=float)
        parametric_coordinates = np.asarray(inputs["parametric_coordinates"], dtype=float).reshape(-1, 3)
        d_evaluated_points = np.asarray(inputs["d_evaluated_points"], dtype=float).reshape(-1, self.model.physical_dimension)

        d_coefficients, d_parametric_coordinates = self.model.compute_vjp(
            coefficients,
            parametric_coordinates,
            d_evaluated_points,
        )
        outputs["d_coefficients"] = d_coefficients
        outputs["d_parametric_coordinates"] = d_parametric_coordinates


class FunctionSetEvaluationOperation(csdl.experimental.CustomExplicitOperationBeta):
    """CSDL custom operation wrapping fixed-coordinate evaluation.

    ``evaluate`` declares the CSDL inputs and output; ``compute`` delegates to
    :meth:`FunctionSetEvaluationModel.evaluate`.
    """
    def __init__(self, model: FunctionSetEvaluationModel):
        super().__init__()
        self.model = model

    def evaluate(self, coefficients, parametric_coordinates):
        """Declare the coefficient input and the evaluated-point output.

        Returns
        -------
        csdl_alpha.Variable
            Points of shape ``(num_coordinates, physical_dimension)``.
        """
        parametric_coordinates = parametric_coordinates.reshape(-1, 3)

        self.declare_input("coefficients", coefficients)
        self.declare_input("parametric_coordinates", parametric_coordinates)

        evaluated_points = self.create_output(
            "evaluated_points",
            (parametric_coordinates.shape[0], self.model.physical_dimension),
        )

        self.declare_vjp_function(
            FunctionSetEvaluationVJP,
            model=self.model,
        )

        return evaluated_points

    def compute(self, inputs, outputs):
        """Evaluate the surface into ``outputs``."""
        coefficients = np.asarray(inputs["coefficients"], dtype=float)
        parametric_coordinates = np.asarray(inputs["parametric_coordinates"], dtype=float).reshape(-1, 3)
        outputs["evaluated_points"] = self.model.evaluate(coefficients, parametric_coordinates)


if __name__ == "__main__":
    try:
        from .function_set_closest_distance_custom_op import (
            _build_demo_function_set,
            stack_function_set_coefficients,
        )
    except ImportError:
        from bsm3.core.projections.function_set_closest_distance_custom_op import (
            _build_demo_function_set,
            stack_function_set_coefficients,
        )

    setup_recorder = csdl.Recorder(inline=True)
    setup_recorder.start()
    function_set = _build_demo_function_set()
    setup_recorder.stop()

    evaluation_model = FunctionSetEvaluationModel(function_set=function_set)
    stacked_coefficients = stack_function_set_coefficients(function_set, evaluation_model.patch_ids)
    parametric_coordinates = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    direct_points = np.asarray(
        function_set.evaluate(
            parametric_coordinates=[
                (int(row[0]), np.asarray(row[1:3], dtype=float).copy())
                for row in parametric_coordinates
            ],
            non_csdl=True,
        ),
        dtype=float,
    ).reshape(-1, 3)

    recorder = csdl.Recorder(inline=True)
    recorder.start()

    coefficients_csdl = csdl.Variable(name="evaluation_stacked_coefficients", value=stacked_coefficients)
    parametric_coordinates_csdl = csdl.Variable(
        name="evaluation_parametric_coordinates",
        value=parametric_coordinates,
    )
    coefficients_csdl.set_as_design_variable()
    parametric_coordinates_csdl.set_as_design_variable()

    evaluation_op = FunctionSetEvaluationOperation(model=evaluation_model)
    evaluated_points = evaluation_op.evaluate(
        coefficients=coefficients_csdl,
        parametric_coordinates=parametric_coordinates_csdl,
    )
    weights = np.linspace(0.15, 1.15, evaluated_points.shape[0] * evaluated_points.shape[1], dtype=float).reshape(
        evaluated_points.shape
    )
    weights[1::2] *= -1.0
    weights_csdl = csdl.Variable(name="evaluation_weights", value=weights)
    objective = csdl.sum(evaluated_points * weights_csdl)
    objective.name = "evaluation_sum"
    objective.set_as_objective()
    d_objective_d_parametric = csdl.derivative(objective, parametric_coordinates_csdl)

    recorder.stop()
    sim = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
    sim.run()

    d_parametric = np.asarray(d_objective_d_parametric.value, dtype=float).reshape(parametric_coordinates.shape)

    print("")
    print("Evaluation baseline output:", evaluated_points.value)
    print(
        "Direct function-set consistency:",
        float(np.max(np.abs(np.asarray(evaluated_points.value, dtype=float) - direct_points))),
    )
    print("Patch-index derivative column:", d_parametric[:, 0])
    sim.check_optimization_derivatives(step_size=1e-7, raise_on_error=False)
