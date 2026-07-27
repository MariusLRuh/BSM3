"""Fixed-set, differentiable tangential smoothing with OML reprojection.

This module implements a deliberately small post-predictor stage.  Its active
vertex set, graph stencil, reference normals, iteration count, and relaxation
are all fixed at setup time.  Consequently, the CSDL graph has no
quality-dependent active-set changes or iteration-count branches.

The smoother preserves the reference-mesh Laplacian coordinates by default:

``x_i <- x_i + omega P_i[(W x)_i - x_i - ((W X)_i - X_i)]``

where ``X`` is the baseline mesh, ``W`` contains positive normalized
inverse-edge-length weights, and ``P_i = I - n_i n_i^T`` is the fixed
reference tangent projector.  Only ``active_ids`` are overwritten; the exact
seam and the outer band ring therefore remain pinned when they are excluded
from that fixed set.

``projection_mode`` fixes, at setup time, when the OML projection runs:

* ``every_iteration`` -- the active vertices are projected back onto their
  prescribed CAD component after *every* Jacobi update (one active-band
  projection per iteration).
* ``final_only`` -- the fixed Jacobi/tangential updates run with no internal
  projection; the smoother returns the preprojected mesh so a single ordinary
  projection of the complete free/non-reevaluated set (in ``run_graph_load_steps``)
  covers the active band together with the rest of the deformation rows.  Because
  the tangent projector uses fixed reference normals, several unprojected
  iterations may drift off a curved OML before that final projection pulls them
  back.

Both modes are differentiable for a fixed closest-projection CAD branch; the
mode itself is fixed setup data, so there is no active-set or branch
discontinuity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

import csdl_alpha as csdl
import numpy as np
import scipy.sparse as sp

from bsm3.preprocessing import ProjectionMetadata
from bsm3.preprocessing.mesh_io import _as_mesh_data

from .projection import project_onto_oml


@dataclass(frozen=True)
class FixedProjectedTangentialSmoother:
    """Immutable data for a fixed-count projected Jacobi smoother."""

    active_ids: np.ndarray
    fixed_neighbor_ids: np.ndarray
    neighbor_average: sp.csc_matrix
    reference_normals: np.ndarray
    reference_laplacian: np.ndarray
    projection_metadata: tuple[ProjectionMetadata, ...]
    num_mesh_vertices: int
    iterations: int
    relaxation: float
    preserve_reference: bool
    projection_mode: Literal["every_iteration", "final_only"] = "every_iteration"

    def evaluate(
        self,
        mesh_vertices,
        *,
        component_coefficients: Mapping[object, object] | None = None,
        projection_options: Mapping[str, object] | None = None,
    ) -> csdl.Variable:
        """Apply the fixed smoother and return all mesh vertices.

        Every operation is differentiable for a fixed closest-projection CAD
        branch.  As with any closest-point projection, a CAD-patch branch
        switch is only piecewise differentiable; there is no dynamic
        element-quality active set in this stage.

        In ``final_only`` mode the returned active rows are *not* yet on the OML;
        the caller is responsible for the single ordinary projection that pulls
        the whole free/non-reevaluated set back onto the deformed OML.
        """

        if tuple(mesh_vertices.shape) != (self.num_mesh_vertices, 3):
            raise ValueError(
                "mesh_vertices must have shape "
                f"({self.num_mesh_vertices}, 3), got {mesh_vertices.shape}."
            )

        current = mesh_vertices * 1.0
        normals = csdl.Variable(value=self.reference_normals)
        reference_laplacian = csdl.Variable(value=self.reference_laplacian)
        active_slice = _row_slice(self.active_ids)

        for _ in range(self.iterations):
            active = current[active_slice]
            neighbor_centroids = csdl.sparse.matmat(
                self.neighbor_average,
                current,
            )
            residual = neighbor_centroids - active
            if self.preserve_reference:
                residual = residual - reference_laplacian

            normal_component = csdl.expand(
                csdl.sum(residual * normals, axes=(1,)),
                normals.shape,
                action="i->ij",
            )
            tangent_update = residual - normals * normal_component
            candidate = active + self.relaxation * tangent_update

            if self.projection_mode == "final_only":
                # Defer the OML projection to the single ordinary projection of
                # the complete free/non-reevaluated set in run_graph_load_steps.
                current = current.set(active_slice, candidate)
                continue

            projected = project_onto_oml(
                deformed_mesh_vertices=candidate,
                deformed_mesh_vertex_ids=self.active_ids,
                projection_metadata=self.projection_metadata,
                component_coefficients=component_coefficients,
                projection_options=dict(projection_options or {}),
            )
            current = current.set(active_slice, projected.values)
        return current


def assemble_fixed_projected_tangential_smoother(
    mesh,
    *,
    active_ids: np.ndarray,
    projection_metadata: Sequence[ProjectionMetadata],
    iterations: int = 3,
    relaxation: float = 0.25,
    preserve_reference: bool = True,
    projection_mode: Literal["every_iteration", "final_only"] = "every_iteration",
    edge_length_floor: float = 1e-12,
) -> FixedProjectedTangentialSmoother:
    """Assemble positive fixed weights and reference tangent projectors.

    ``active_ids`` is supplied explicitly and is never modified at evaluation
    time.  Immediate graph neighbors outside this set are reported as
    ``fixed_neighbor_ids`` and remain unchanged by the smoother.

    ``projection_mode`` (``every_iteration`` or ``final_only``) is fixed setup
    data; see the module docstring for the semantics.
    """

    mesh_data = _as_mesh_data(mesh)
    points = np.asarray(mesh_data.vertices, dtype=float).reshape((-1, 3))
    ids = np.asarray(active_ids, dtype=np.int64).reshape(-1)
    if ids.size == 0:
        raise ValueError("active_ids must contain at least one vertex.")
    if np.unique(ids).size != ids.size:
        raise ValueError("active_ids must be unique.")
    if np.any(ids < 0) or np.any(ids >= points.shape[0]):
        raise ValueError("active_ids contains an out-of-range vertex.")

    count = int(iterations)
    if count < 1 or count != iterations:
        raise ValueError("iterations must be a positive integer.")
    omega = float(relaxation)
    if not np.isfinite(omega) or not 0.0 < omega <= 1.0:
        raise ValueError("relaxation must lie in (0, 1].")
    if projection_mode not in ("every_iteration", "final_only"):
        raise ValueError(
            "projection_mode must be 'every_iteration' or 'final_only'."
        )
    length_floor = float(edge_length_floor)
    if not np.isfinite(length_floor) or length_floor <= 0.0:
        raise ValueError("edge_length_floor must be positive.")

    adjacency = _ring_adjacency(mesh_data, points.shape[0])
    rows = []
    columns = []
    values = []
    fixed_neighbors: set[int] = set()
    active_set = set(int(item) for item in ids)
    for row, vertex_id in enumerate(ids):
        neighbors = np.asarray(sorted(adjacency[int(vertex_id)]), dtype=np.int64)
        if neighbors.size == 0:
            raise ValueError(
                f"Active vertex {int(vertex_id)} has no surface-graph neighbors."
            )
        lengths = np.linalg.norm(
            points[neighbors] - points[int(vertex_id)],
            axis=1,
        )
        inverse_lengths = 1.0 / np.maximum(lengths, length_floor)
        weights = inverse_lengths / np.sum(inverse_lengths)
        rows.extend([row] * neighbors.size)
        columns.extend(neighbors.tolist())
        values.extend(weights.tolist())
        fixed_neighbors.update(
            int(neighbor)
            for neighbor in neighbors
            if int(neighbor) not in active_set
        )
    neighbor_average = sp.csc_matrix(
        (values, (rows, columns)),
        shape=(ids.size, points.shape[0]),
    )

    reference_normals = _area_weighted_vertex_normals(
        mesh_data,
        points,
        ids,
        adjacency,
    )
    reference_laplacian = (
        np.asarray(neighbor_average @ points, dtype=float) - points[ids]
    )
    if not preserve_reference:
        reference_laplacian = np.zeros_like(reference_laplacian)

    metadata = tuple(projection_metadata)
    if not metadata:
        raise ValueError("projection_metadata must contain at least one group.")
    metadata_ids = np.concatenate(
        [
            np.asarray(group.vertex_ids, dtype=np.int64).reshape(-1)
            for group in metadata
        ]
    )
    missing = np.setdiff1d(ids, metadata_ids)
    if missing.size:
        raise ValueError(
            "projection_metadata does not cover every active vertex; "
            f"first missing IDs: {missing[:10].tolist()}."
        )

    return FixedProjectedTangentialSmoother(
        active_ids=ids.copy(),
        fixed_neighbor_ids=np.asarray(sorted(fixed_neighbors), dtype=np.int64),
        neighbor_average=neighbor_average,
        reference_normals=reference_normals,
        reference_laplacian=reference_laplacian,
        projection_metadata=metadata,
        num_mesh_vertices=points.shape[0],
        iterations=count,
        relaxation=omega,
        preserve_reference=bool(preserve_reference),
        projection_mode=projection_mode,
    )


def _ring_adjacency(mesh_data, num_vertices: int) -> list[set[int]]:
    adjacency = [set() for _ in range(int(num_vertices))]
    for block in mesh_data.cell_blocks.values():
        cells = np.asarray(block, dtype=np.int64)
        if cells.ndim != 2 or cells.shape[1] < 2:
            continue
        for cell in cells:
            for local_index, vertex_a in enumerate(cell):
                vertex_b = int(cell[(local_index + 1) % cell.size])
                vertex_a = int(vertex_a)
                if vertex_a == vertex_b:
                    continue
                adjacency[vertex_a].add(vertex_b)
                adjacency[vertex_b].add(vertex_a)
    return adjacency


def _area_weighted_vertex_normals(
    mesh_data,
    points: np.ndarray,
    active_ids: np.ndarray,
    adjacency: list[set[int]],
) -> np.ndarray:
    accumulated = np.zeros_like(points)
    for block in mesh_data.cell_blocks.values():
        cells = np.asarray(block, dtype=np.int64)
        if cells.ndim != 2 or cells.shape[1] < 3:
            continue
        for cell in cells:
            polygon = points[cell]
            area_vector = np.sum(
                np.cross(polygon, np.roll(polygon, -1, axis=0)),
                axis=0,
            )
            accumulated[cell] += area_vector

    normals = accumulated[active_ids].copy()
    magnitudes = np.linalg.norm(normals, axis=1)
    for row in np.where(magnitudes <= 1e-14)[0]:
        vertex_id = int(active_ids[row])
        neighbor_ids = np.asarray(
            sorted(adjacency[vertex_id]),
            dtype=np.int64,
        )
        local = points[neighbor_ids] - points[vertex_id]
        if local.shape[0] < 2:
            raise ValueError(
                f"Cannot construct a tangent plane at vertex {vertex_id}."
            )
        _, singular_values, right_vectors = np.linalg.svd(
            local,
            full_matrices=False,
        )
        if singular_values.size < 2 or singular_values[1] <= 1e-14:
            raise ValueError(
                f"Cannot construct a tangent plane at collinear vertex {vertex_id}."
            )
        normals[row] = right_vectors[-1]
    magnitudes = np.linalg.norm(normals, axis=1)
    return normals / magnitudes[:, None]


def _row_slice(rows):
    rows = np.asarray(rows, dtype=np.int64).reshape(-1)
    if rows.size == 1:
        row = int(rows[0])
        return csdl.slice[row : row + 1, :]
    return csdl.slice[rows.tolist(), :]


__all__ = [
    "FixedProjectedTangentialSmoother",
    "assemble_fixed_projected_tangential_smoother",
]
