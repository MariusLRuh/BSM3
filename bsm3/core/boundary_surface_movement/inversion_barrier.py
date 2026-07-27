"""Differentiable local barrier repair for polygon corner inversions.

The surface quality metric used by this package is the sign of every original
polygon corner Jacobian relative to that polygon's baseline normal.  This module
optimizes that exact metric; it does not rely on an internal triangulation.

The forward solve is local because a valid candidate needs no repair.  Corners
below an activation margin select a buffered element patch, and L-BFGS minimizes
a quadratic proximity term plus a squared orientation barrier on that patch.
The custom VJP differentiates the converged stationarity equations with the
implicit function theorem.  The buffered activation margin keeps the discrete
patch selection away from the zero-orientation boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

import csdl_alpha as csdl
import numpy as np
from scipy.optimize import minimize

from bsm3.preprocessing.mesh_io import _as_mesh_data


@dataclass(frozen=True)
class BarrierSolveInfo:
    active_free_nodes: int
    iterations: int
    minimum_oriented_ratio: float
    penalty_weight: float


@dataclass(frozen=True)
class _BarrierState:
    free_positions: np.ndarray
    all_positions: np.ndarray
    active_nodes: np.ndarray
    support_corner_ids: np.ndarray
    penalty_weight: float
    iterations: int


class CornerInversionBarrierModel:
    """Setup-time topology and nonlinear corner-barrier solve."""

    def __init__(
        self,
        mesh,
        *,
        free_ids: np.ndarray,
        prescribed_ids: np.ndarray,
        activation_margin: float = 0.2,
        target_margin: float = 0.05,
        proximity_weight: float = 1.0,
        barrier_weight: float = 500.0,
        max_iterations: int = 300,
        tolerance: float = 1e-11,
        verbose: bool = False,
    ):
        if not (0.0 < float(target_margin) < float(activation_margin)):
            raise ValueError(
                "Require 0 < target_margin < activation_margin for a buffered "
                "barrier active set."
            )
        if float(proximity_weight) <= 0.0 or float(barrier_weight) <= 0.0:
            raise ValueError("Barrier and proximity weights must be positive.")
        if int(max_iterations) <= 0:
            raise ValueError("max_iterations must be positive.")

        mesh_data = _as_mesh_data(mesh)
        self.baseline = np.asarray(mesh_data.vertices, dtype=float).reshape((-1, 3))
        self.free_ids = np.asarray(free_ids, dtype=np.int64).reshape(-1)
        self.prescribed_ids = np.asarray(prescribed_ids, dtype=np.int64).reshape(-1)
        if np.intersect1d(self.free_ids, self.prescribed_ids).size:
            raise ValueError("Barrier free and prescribed vertex sets must be disjoint.")
        self.activation_margin = float(activation_margin)
        self.target_margin = float(target_margin)
        self.proximity_weight = float(proximity_weight)
        self.barrier_weight = float(barrier_weight)
        self.max_iterations = int(max_iterations)
        self.tolerance = float(tolerance)
        self.verbose = bool(verbose)

        self.all_ids = np.concatenate((self.free_ids, self.prescribed_ids))
        self._all_local = {
            int(vertex): row for row, vertex in enumerate(self.all_ids)
        }
        free_set = set(int(vertex) for vertex in self.free_ids)
        classified = set(self._all_local)

        cells: list[np.ndarray] = []
        for block in mesh_data.cell_blocks.values():
            block_array = np.asarray(block, dtype=np.int64)
            if block_array.ndim != 2 or block_array.shape[1] < 3:
                continue
            for cell in block_array:
                if not any(int(vertex) in free_set for vertex in cell):
                    continue
                missing = [int(vertex) for vertex in cell if int(vertex) not in classified]
                if missing:
                    raise ValueError(
                        "Barrier support has unclassified co-element vertices "
                        f"{missing[:10]}; prescribed_ids must be an element halo."
                    )
                cells.append(
                    np.asarray(
                        [self._all_local[int(vertex)] for vertex in cell],
                        dtype=np.int64,
                    )
                )
        if not cells:
            raise ValueError("No surface cells touch the barrier free set.")
        self.cells = tuple(cells)

        previous = []
        center = []
        following = []
        normals = []
        inverse_reference_jacobian = []
        corner_cells = []
        edge_lengths = []
        for cell_index, local_cell in enumerate(self.cells):
            global_cell = self.all_ids[local_cell]
            polygon = self.baseline[global_cell]
            normal = np.sum(
                np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0
            )
            normal_norm = float(np.linalg.norm(normal))
            if normal_norm <= 1e-14:
                raise ValueError("Barrier support contains a degenerate polygon.")
            normal /= normal_norm
            edge_lengths.extend(
                np.linalg.norm(
                    polygon - np.roll(polygon, 1, axis=0), axis=1
                ).tolist()
            )
            for index, local_center in enumerate(local_cell):
                local_previous = int(local_cell[index - 1])
                local_following = int(local_cell[(index + 1) % local_cell.size])
                reference_jacobian = float(
                    np.dot(
                        np.cross(
                            self.baseline[self.all_ids[int(local_center)]]
                            - self.baseline[self.all_ids[local_previous]],
                            self.baseline[self.all_ids[local_following]]
                            - self.baseline[self.all_ids[local_previous]],
                        ),
                        normal,
                    )
                )
                if reference_jacobian <= 0.0:
                    raise ValueError(
                        "Baseline polygon has a non-positive corner orientation."
                    )
                previous.append(local_previous)
                center.append(int(local_center))
                following.append(local_following)
                normals.append(normal)
                inverse_reference_jacobian.append(1.0 / reference_jacobian)
                corner_cells.append(cell_index)

        self.previous = np.asarray(previous, dtype=np.int64)
        self.center = np.asarray(center, dtype=np.int64)
        self.following = np.asarray(following, dtype=np.int64)
        self.normals = np.asarray(normals, dtype=float)
        self.inverse_reference_jacobian = np.asarray(
            inverse_reference_jacobian, dtype=float
        )
        self.corner_cells = np.asarray(corner_cells, dtype=np.int64)
        self.length_scale = max(float(np.median(edge_lengths)), 1e-12)
        self._data_coefficient = self.proximity_weight / self.length_scale**2

        cells_by_node: list[list[int]] = [[] for _ in range(self.all_ids.size)]
        for cell_index, cell in enumerate(self.cells):
            for node in cell:
                cells_by_node[int(node)].append(cell_index)
        self.cells_by_node = tuple(
            np.asarray(sorted(set(items)), dtype=np.int64)
            for items in cells_by_node
        )

    def solve(
        self,
        free_positions: np.ndarray,
        prescribed_positions: np.ndarray,
        *,
        return_state: bool = False,
    ):
        free_positions = np.asarray(free_positions, dtype=float).reshape((-1, 3))
        prescribed_positions = np.asarray(
            prescribed_positions, dtype=float
        ).reshape((-1, 3))
        if free_positions.shape[0] != self.free_ids.size:
            raise ValueError("free_positions does not align with free_ids.")
        if prescribed_positions.shape[0] != self.prescribed_ids.size:
            raise ValueError("prescribed_positions does not align with prescribed_ids.")
        candidate = np.vstack((free_positions, prescribed_positions))
        ratios = self._corner_ratios(candidate)
        low_corner_ids = np.where(ratios < self.activation_margin)[0]
        if low_corner_ids.size == 0:
            state = _BarrierState(
                free_positions=free_positions.copy(),
                all_positions=candidate,
                active_nodes=np.empty(0, dtype=np.int64),
                support_corner_ids=np.empty(0, dtype=np.int64),
                penalty_weight=self.barrier_weight,
                iterations=0,
            )
            info = BarrierSolveInfo(
                active_free_nodes=0,
                iterations=0,
                minimum_oriented_ratio=float(np.min(ratios)),
                penalty_weight=self.barrier_weight,
            )
            return (state.free_positions, state, info) if return_state else state.free_positions

        low_cells = np.unique(self.corner_cells[low_corner_ids])
        patch_nodes = set(
            int(node) for cell in low_cells for node in self.cells[int(cell)]
        )
        # Two cell layers give the repair room to redistribute a corner motion
        # without creating a new defect immediately outside the selected patch.
        for _ in range(2):
            patch_cells = set(
                int(cell)
                for node in patch_nodes
                for cell in self.cells_by_node[node]
            )
            patch_nodes.update(
                int(node) for cell in patch_cells for node in self.cells[cell]
            )
        active_nodes = np.asarray(
            sorted(node for node in patch_nodes if node < self.free_ids.size),
            dtype=np.int64,
        )
        if active_nodes.size == 0:
            raise RuntimeError("An inverted corner patch contains no free vertices.")
        support_cells = set(
            int(cell)
            for node in active_nodes
            for cell in self.cells_by_node[int(node)]
        )
        support_corner_ids = np.where(
            np.isin(self.corner_cells, np.asarray(sorted(support_cells), dtype=np.int64))
        )[0].astype(np.int64)

        result = None
        working = candidate.copy()
        total_iterations = 0
        used_weight = self.barrier_weight
        for multiplier in (1.0, 10.0, 100.0):
            used_weight = self.barrier_weight * multiplier
            objective = self._objective(
                candidate=candidate,
                working=working,
                active_nodes=active_nodes,
                support_corner_ids=support_corner_ids,
                penalty_weight=used_weight,
            )
            result = minimize(
                objective,
                working[active_nodes].reshape(-1),
                method="L-BFGS-B",
                jac=True,
                options={
                    "maxiter": self.max_iterations,
                    "ftol": self.tolerance,
                    "gtol": 1e-8,
                    "maxls": 50,
                },
            )
            working[active_nodes] = np.asarray(result.x, dtype=float).reshape((-1, 3))
            total_iterations += int(result.nit)
            minimum = float(np.min(self._corner_ratios(working)))
            if minimum > 1e-8:
                break
        if result is None or minimum <= 0.0:
            raise RuntimeError(
                "Corner barrier failed to produce an orientation-positive mesh; "
                f"minimum normalized corner Jacobian is {minimum:+.3e}."
            )

        state = _BarrierState(
            free_positions=working[: self.free_ids.size].copy(),
            all_positions=working.copy(),
            active_nodes=active_nodes,
            support_corner_ids=support_corner_ids,
            penalty_weight=used_weight,
            iterations=total_iterations,
        )
        info = BarrierSolveInfo(
            active_free_nodes=int(active_nodes.size),
            iterations=total_iterations,
            minimum_oriented_ratio=minimum,
            penalty_weight=used_weight,
        )
        return (state.free_positions, state, info) if return_state else state.free_positions

    def select_candidate(
        self,
        primary_free_positions: np.ndarray,
        fallback_free_positions: np.ndarray,
        prescribed_positions: np.ndarray,
    ) -> str:
        """Choose the candidate with fewer non-positive original corners."""

        prescribed_positions = np.asarray(prescribed_positions, dtype=float).reshape((-1, 3))
        counts = []
        minima = []
        for candidate in (primary_free_positions, fallback_free_positions):
            all_positions = np.vstack(
                (
                    np.asarray(candidate, dtype=float).reshape((-1, 3)),
                    prescribed_positions,
                )
            )
            ratios = self._corner_ratios(all_positions)
            counts.append(int(np.count_nonzero(ratios <= 0.0)))
            minima.append(float(np.min(ratios)))
        if counts[0] < counts[1]:
            return "primary"
        if counts[1] < counts[0]:
            return "fallback"
        return "primary" if minima[0] >= minima[1] else "fallback"

    def compute_vjp(
        self,
        free_positions: np.ndarray,
        prescribed_positions: np.ndarray,
        d_repaired_free_positions: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        _, state, _ = self.solve(
            free_positions, prescribed_positions, return_state=True
        )
        cotangent = np.asarray(
            d_repaired_free_positions, dtype=float
        ).reshape((-1, 3))
        if state.active_nodes.size == 0:
            return cotangent.copy(), np.zeros_like(prescribed_positions, dtype=float)

        support_nodes, corner_hessian = self._barrier_hessian(
            state.all_positions,
            state.support_corner_ids,
            state.penalty_weight,
        )
        support_local = {
            int(node): row for row, node in enumerate(support_nodes)
        }
        active_support_rows = np.asarray(
            [support_local[int(node)] for node in state.active_nodes],
            dtype=np.int64,
        )
        active_dofs = (
            3 * active_support_rows[:, None]
            + np.arange(3, dtype=np.int64)[None, :]
        ).reshape(-1)
        hessian_active = corner_hessian[np.ix_(active_dofs, active_dofs)].copy()
        hessian_active.flat[:: hessian_active.shape[0] + 1] += self._data_coefficient
        d_active = cotangent[state.active_nodes].reshape(-1)
        try:
            adjoint = np.linalg.solve(hessian_active.T, d_active)
        except np.linalg.LinAlgError:
            regularization = 1e-10 * max(
                1.0, float(np.max(np.abs(np.diag(hessian_active))))
            )
            adjoint = np.linalg.solve(
                hessian_active.T + regularization * np.eye(hessian_active.shape[0]),
                d_active,
            )

        fixed_bar_support = -(
            corner_hessian[active_dofs, :].T @ adjoint
        ).reshape((-1, 3))
        fixed_bar_support[active_support_rows] = 0.0
        d_free = cotangent.copy()
        d_free[state.active_nodes] = (
            self._data_coefficient * adjoint.reshape((-1, 3))
        )
        d_prescribed = np.zeros_like(prescribed_positions, dtype=float)
        for support_row, node in enumerate(support_nodes):
            node = int(node)
            if node < self.free_ids.size:
                d_free[node] += fixed_bar_support[support_row]
            else:
                d_prescribed[node - self.free_ids.size] += fixed_bar_support[
                    support_row
                ]
        return d_free, d_prescribed

    def _objective(
        self,
        *,
        candidate,
        working,
        active_nodes,
        support_corner_ids,
        penalty_weight,
    ):
        base_active = candidate[active_nodes].copy()
        p = self.previous[support_corner_ids]
        q = self.center[support_corner_ids]
        r = self.following[support_corner_ids]
        normals = self.normals[support_corner_ids]
        inverse_reference = self.inverse_reference_jacobian[support_corner_ids]

        def objective(values):
            working[active_nodes] = np.asarray(values, dtype=float).reshape((-1, 3))
            difference = working[active_nodes] - base_active
            value = 0.5 * self._data_coefficient * float(
                np.sum(difference * difference)
            )
            gradient_all = np.zeros_like(working)
            gradient_all[active_nodes] = self._data_coefficient * difference

            edge_q = working[q] - working[p]
            edge_r = working[r] - working[p]
            ratios = (
                np.einsum("ij,ij->i", np.cross(edge_q, edge_r), normals)
                * inverse_reference
            )
            violating = ratios < self.target_margin
            if np.any(violating):
                delta = ratios[violating] - self.target_margin
                value += 0.5 * penalty_weight * float(np.dot(delta, delta))
                grad_q, grad_r, grad_p = _corner_ratio_gradients(
                    edge_q[violating],
                    edge_r[violating],
                    normals[violating],
                    inverse_reference[violating],
                )
                scale = penalty_weight * delta[:, None]
                np.add.at(gradient_all, q[violating], scale * grad_q)
                np.add.at(gradient_all, r[violating], scale * grad_r)
                np.add.at(gradient_all, p[violating], scale * grad_p)
            return value, gradient_all[active_nodes].reshape(-1)

        return objective

    def _corner_ratios(self, positions):
        edge_q = positions[self.center] - positions[self.previous]
        edge_r = positions[self.following] - positions[self.previous]
        return (
            np.einsum("ij,ij->i", np.cross(edge_q, edge_r), self.normals)
            * self.inverse_reference_jacobian
        )

    def _barrier_hessian(self, positions, corner_ids, penalty_weight):
        support_nodes = np.unique(
            np.concatenate(
                (
                    self.previous[corner_ids],
                    self.center[corner_ids],
                    self.following[corner_ids],
                )
            )
        ).astype(np.int64)
        support_local = {
            int(node): row for row, node in enumerate(support_nodes)
        }
        size = 3 * support_nodes.size
        hessian = np.zeros((size, size), dtype=float)
        for corner_id in corner_ids:
            p = int(self.previous[corner_id])
            q = int(self.center[corner_id])
            r = int(self.following[corner_id])
            normal = self.normals[corner_id]
            inverse_reference = float(self.inverse_reference_jacobian[corner_id])
            edge_q = positions[q] - positions[p]
            edge_r = positions[r] - positions[p]
            ratio = float(np.dot(np.cross(edge_q, edge_r), normal)) * inverse_reference
            if ratio >= self.target_margin:
                continue
            grad_q, grad_r, grad_p = _corner_ratio_gradients(
                edge_q[None, :],
                edge_r[None, :],
                normal[None, :],
                np.asarray((inverse_reference,)),
            )
            gradient = np.concatenate((grad_p[0], grad_q[0], grad_r[0]))
            ratio_hessian = _corner_ratio_hessian(normal, inverse_reference)
            local_hessian = penalty_weight * (
                np.outer(gradient, gradient)
                + (ratio - self.target_margin) * ratio_hessian
            )
            dofs = np.asarray(
                [
                    3 * support_local[node] + component
                    for node in (p, q, r)
                    for component in range(3)
                ],
                dtype=np.int64,
            )
            hessian[np.ix_(dofs, dofs)] += local_hessian
        return support_nodes, hessian


def _corner_ratio_gradients(edge_q, edge_r, normals, inverse_reference):
    grad_q = np.cross(edge_r, normals) * inverse_reference[:, None]
    grad_r = np.cross(normals, edge_q) * inverse_reference[:, None]
    return grad_q, grad_r, -grad_q - grad_r


def _corner_ratio_hessian(normal, inverse_reference):
    """Constant 9x9 Hessian in the node order ``(previous, center, next)``."""

    hessian = np.zeros((9, 9), dtype=float)
    zero = np.zeros((3, 3), dtype=float)
    for column in range(9):
        coordinates = zero.copy()
        coordinates.reshape(-1)[column] = 1.0
        edge_q = coordinates[1] - coordinates[0]
        edge_r = coordinates[2] - coordinates[0]
        grad_q, grad_r, grad_p = _corner_ratio_gradients(
            edge_q[None, :],
            edge_r[None, :],
            np.asarray(normal, dtype=float).reshape((1, 3)),
            np.asarray((inverse_reference,), dtype=float),
        )
        hessian[:, column] = np.concatenate((grad_p[0], grad_q[0], grad_r[0]))
    return 0.5 * (hessian + hessian.T)


class CornerInversionBarrierOperation(
    csdl.experimental.CustomExplicitOperationBeta
):
    """CSDL wrapper around the local nonlinear barrier solve."""

    def __init__(self, model: CornerInversionBarrierModel):
        super().__init__()
        self.model = model

    def evaluate(self, free_positions, prescribed_positions):
        self.declare_input("free_positions", free_positions)
        self.declare_input("prescribed_positions", prescribed_positions)
        repaired = self.create_output("repaired_free_positions", free_positions.shape)
        self.declare_vjp_function(
            CornerInversionBarrierVJP,
            model=self.model,
        )
        return repaired

    def compute(self, inputs, outputs):
        outputs["repaired_free_positions"] = self.model.solve(
            inputs["free_positions"],
            inputs["prescribed_positions"],
        )


class CornerInversionBarrierVJP(
    csdl.experimental.CustomExplicitOperationBeta
):
    """IFT adjoint of the converged local barrier equilibrium."""

    def __init__(self, model: CornerInversionBarrierModel):
        super().__init__()
        self.model = model

    def evaluate(self, inputs, d_outputs):
        free_positions = inputs["free_positions"]
        prescribed_positions = inputs["prescribed_positions"]
        d_repaired = d_outputs["repaired_free_positions"]
        self.declare_input("free_positions", free_positions)
        self.declare_input("prescribed_positions", prescribed_positions)
        self.declare_input("d_repaired_free_positions", d_repaired)
        d_free = self.create_output("d_free_positions", free_positions.shape)
        d_prescribed = self.create_output(
            "d_prescribed_positions", prescribed_positions.shape
        )
        return {
            "free_positions": d_free,
            "prescribed_positions": d_prescribed,
        }

    def compute(self, inputs, outputs):
        d_free, d_prescribed = self.model.compute_vjp(
            inputs["free_positions"],
            inputs["prescribed_positions"],
            inputs["d_repaired_free_positions"],
        )
        outputs["d_free_positions"] = d_free
        outputs["d_prescribed_positions"] = d_prescribed


class FallbackCornerInversionBarrierOperation(
    csdl.experimental.CustomExplicitOperationBeta
):
    """Barrier repair with a deterministic secondary candidate.

    The membrane solution is the primary candidate and the established graph
    solution is the fallback.  Selection uses only the count/sign of the exact
    original-polygon corner metric, then the same nonlinear barrier repairs the
    selected candidate.
    """

    def __init__(self, model: CornerInversionBarrierModel):
        super().__init__()
        self.model = model

    def evaluate(
        self,
        primary_free_positions,
        fallback_free_positions,
        prescribed_positions,
    ):
        self.declare_input("primary_free_positions", primary_free_positions)
        self.declare_input("fallback_free_positions", fallback_free_positions)
        self.declare_input("prescribed_positions", prescribed_positions)
        repaired = self.create_output(
            "repaired_free_positions", primary_free_positions.shape
        )
        self.declare_vjp_function(
            FallbackCornerInversionBarrierVJP,
            model=self.model,
        )
        return repaired

    def compute(self, inputs, outputs):
        selected = self.model.select_candidate(
            inputs["primary_free_positions"],
            inputs["fallback_free_positions"],
            inputs["prescribed_positions"],
        )
        candidate = inputs[
            "primary_free_positions"
            if selected == "primary"
            else "fallback_free_positions"
        ]
        repaired, _, info = self.model.solve(
            candidate,
            inputs["prescribed_positions"],
            return_state=True,
        )
        outputs["repaired_free_positions"] = repaired
        if self.model.verbose:
            print(
                "[barrier] "
                f"candidate={selected} active_free={info.active_free_nodes} "
                f"iterations={info.iterations} "
                f"min_oriented_ratio={info.minimum_oriented_ratio:+.3e} "
                f"penalty={info.penalty_weight:g}",
                flush=True,
            )


class FallbackCornerInversionBarrierVJP(
    csdl.experimental.CustomExplicitOperationBeta
):
    """IFT VJP routed through the candidate selected in the forward rule."""

    def __init__(self, model: CornerInversionBarrierModel):
        super().__init__()
        self.model = model

    def evaluate(self, inputs, d_outputs):
        primary = inputs["primary_free_positions"]
        fallback = inputs["fallback_free_positions"]
        prescribed = inputs["prescribed_positions"]
        d_repaired = d_outputs["repaired_free_positions"]
        self.declare_input("primary_free_positions", primary)
        self.declare_input("fallback_free_positions", fallback)
        self.declare_input("prescribed_positions", prescribed)
        self.declare_input("d_repaired_free_positions", d_repaired)
        d_primary = self.create_output("d_primary_free_positions", primary.shape)
        d_fallback = self.create_output("d_fallback_free_positions", fallback.shape)
        d_prescribed = self.create_output(
            "d_prescribed_positions", prescribed.shape
        )
        return {
            "primary_free_positions": d_primary,
            "fallback_free_positions": d_fallback,
            "prescribed_positions": d_prescribed,
        }

    def compute(self, inputs, outputs):
        selected = self.model.select_candidate(
            inputs["primary_free_positions"],
            inputs["fallback_free_positions"],
            inputs["prescribed_positions"],
        )
        key = (
            "primary_free_positions"
            if selected == "primary"
            else "fallback_free_positions"
        )
        d_candidate, d_prescribed = self.model.compute_vjp(
            inputs[key],
            inputs["prescribed_positions"],
            inputs["d_repaired_free_positions"],
        )
        outputs["d_primary_free_positions"] = np.zeros_like(
            inputs["primary_free_positions"], dtype=float
        )
        outputs["d_fallback_free_positions"] = np.zeros_like(
            inputs["fallback_free_positions"], dtype=float
        )
        outputs[
            "d_primary_free_positions"
            if selected == "primary"
            else "d_fallback_free_positions"
        ] = d_candidate
        outputs["d_prescribed_positions"] = d_prescribed


__all__ = [
    "BarrierSolveInfo",
    "CornerInversionBarrierModel",
    "CornerInversionBarrierOperation",
    "CornerInversionBarrierVJP",
    "FallbackCornerInversionBarrierOperation",
    "FallbackCornerInversionBarrierVJP",
]
