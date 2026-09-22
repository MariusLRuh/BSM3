"""Reference-configuration stiffness assembly for mesh-motion propagation.

This module builds the linear system that the physics-based propagator solves
in place of the RBF field.  Milestone 1 uses an isotropic
displacement-difference graph energy

    Phi(u) = 1/2 * sum_{(i,j) in E} w_ij * || u_i - u_j ||^2 ,

whose stationarity under a prescribed-displacement (Dirichlet) split gives, per
Cartesian component,

    L_ff u_f = - L_fp u_p ,

with ``L`` the weighted graph Laplacian of the *reference* mesh.  The three
components decouple and share one factorization of ``L_ff`` (the SPD free-free
block); ``L_fp`` is a constant sparse coupling matrix consumed downstream by
``csdl.sparse.matmat``.

Assembly is setup-time NumPy/scipy: connectivity, edge weights, and the
factorization are constants in the CSDL graph (only ``u_p`` carries gradients).
The free/prescribed split is arbitrary vertex sets, so alternate configurations
(e.g. strut-adjacent bands) reuse the same assembler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import scipy.sparse as sp

from bsm3.preprocessing.mesh_io import _as_mesh_data

from .spd_solve_custom_op import SPDFactor, factorize_spd


@dataclass(frozen=True)
class AssembledSystem:
    """Factored free-free block and constant free-prescribed coupling.

    ``free_ids`` and ``prescribed_ids`` fix the row/column ordering of the
    solve: ``u_f`` rows align with ``free_ids`` and ``u_p`` rows align with
    ``prescribed_ids``.  ``factor`` solves ``L_ff x = rhs`` (and, by symmetry,
    its adjoint); ``coupling`` is ``L_fp`` as a ``(n_free, n_prescribed)``
    sparse matrix.
    """

    free_ids: np.ndarray
    prescribed_ids: np.ndarray
    factor: SPDFactor
    coupling: sp.spmatrix

    @property
    def num_free(self) -> int:
        return int(self.free_ids.size)

    @property
    def num_prescribed(self) -> int:
        return int(self.prescribed_ids.size)


@dataclass(frozen=True)
class CoupledAssembledSystem:
    """Factored coupled 3D free block for a membrane discretization.

    Vertex DOFs use the documented interleave
    ``[x0, y0, z0, x1, y1, z1, ...]`` in the order fixed by ``free_ids`` and
    ``prescribed_ids``.  ``active_free_dofs`` omits any explicitly constrained
    free-vertex components (the symmetry-plane y DOFs); ``scatter`` expands a
    solved active vector back to all ``3 * num_free`` interleaved DOFs.
    """

    free_ids: np.ndarray
    prescribed_ids: np.ndarray
    active_free_dofs: np.ndarray
    factor: SPDFactor
    coupling: sp.spmatrix
    scatter: sp.spmatrix

    @property
    def num_free(self) -> int:
        return int(self.free_ids.size)

    @property
    def num_prescribed(self) -> int:
        return int(self.prescribed_ids.size)

    @property
    def num_active_free_dofs(self) -> int:
        return int(self.active_free_dofs.size)


class StiffnessAssembler(Protocol):
    """Build a factored SPD free-free block and its prescribed coupling."""

    def assemble(
        self,
        mesh,
        *,
        free_ids: np.ndarray,
        prescribed_ids: np.ndarray,
    ) -> AssembledSystem: ...


class GraphLaplacianAssembler:
    """Displacement-difference stiffness: decoupled scalar graph Laplacian.

    Edge weights follow ``w_ij = sum_{f in faces(i,j)} A_f^{-chi}`` with
    ``A_f`` the reference face area.  ``chi = 0`` recovers uniform weights
    (``w_ij = 1`` per graph edge) -- the pure graph Laplacian / harmonic map,
    which is Milestone 1's validated default.  Positive ``chi`` stiffens small
    cells so they resist collapse under large compression.

    When ``quad_diagonal_weight`` is positive, ``quad_bracing_mode`` selects
    one quality-chosen diagonal, both diagonals, or a four-spoke virtual center.
    The center is eliminated analytically, so every mode affects only the
    deformation operator; none alters the aerodynamic mesh connectivity.
    """

    def __init__(
        self,
        *,
        stiffening_exponent: float = 0.0,
        area_floor: float = 1e-12,
        distance_weighting=None,
        quad_diagonal_weight: float = 0.0,
        quad_bracing_mode: str = "both_diagonals",
    ):
        if float(stiffening_exponent) < 0.0:
            raise ValueError("stiffening_exponent (chi) must be non-negative.")
        if float(area_floor) <= 0.0:
            raise ValueError("area_floor must be positive.")
        if (
            not np.isfinite(float(quad_diagonal_weight))
            or float(quad_diagonal_weight) < 0.0
        ):
            raise ValueError("quad_diagonal_weight must be finite and non-negative.")
        _validate_quad_bracing_mode(quad_bracing_mode)
        self.stiffening_exponent = float(stiffening_exponent)
        self.area_floor = float(area_floor)
        self.quad_diagonal_weight = float(quad_diagonal_weight)
        self.quad_bracing_mode = str(quad_bracing_mode)
        # Optional fixed reference-geodesic distance multiplier applied to every
        # edge weight.  ``None`` (or ``beta = 0``) is the exact no-op baseline.
        self.distance_weighting = distance_weighting

    def assemble(
        self,
        mesh,
        *,
        free_ids: np.ndarray,
        prescribed_ids: np.ndarray,
    ) -> AssembledSystem:
        mesh_data = _as_mesh_data(mesh)
        points = np.asarray(mesh_data.vertices, dtype=float).reshape((-1, 3))

        free_ids = np.asarray(free_ids, dtype=np.int64).reshape(-1)
        prescribed_ids = np.asarray(prescribed_ids, dtype=np.int64).reshape(-1)
        if np.intersect1d(free_ids, prescribed_ids).size:
            raise ValueError("free_ids and prescribed_ids must be disjoint.")
        if np.unique(free_ids).size != free_ids.size:
            raise ValueError("free_ids must not contain duplicates.")
        if np.unique(prescribed_ids).size != prescribed_ids.size:
            raise ValueError("prescribed_ids must not contain duplicates.")

        edge_weights = _edge_weights(
            mesh_data,
            points,
            stiffening_exponent=self.stiffening_exponent,
            area_floor=self.area_floor,
            quad_diagonal_weight=self.quad_diagonal_weight,
            quad_bracing_mode=self.quad_bracing_mode,
        )
        if self.distance_weighting is not None:
            # Multiply each reference edge weight by its fixed distance factor.
            # Distances are setup constants, so this preserves symmetry, keeps
            # every weight positive, and leaves the free-free block SPD.
            multipliers = self.distance_weighting.edge_multiplier_map(
                edge_weights.keys()
            )
            edge_weights = {
                key: weight * multipliers[key]
                for key, weight in edge_weights.items()
            }

        free_local = {int(vertex): row for row, vertex in enumerate(free_ids)}
        prescribed_local = {
            int(vertex): row for row, vertex in enumerate(prescribed_ids)
        }
        free_set = set(free_local)
        prescribed_set = set(prescribed_local)

        adjacency: dict[int, dict[int, float]] = {}
        for (vertex_a, vertex_b), weight in edge_weights.items():
            adjacency.setdefault(vertex_a, {})[vertex_b] = weight
            adjacency.setdefault(vertex_b, {})[vertex_a] = weight

        ff_rows: list[int] = []
        ff_cols: list[int] = []
        ff_values: list[float] = []
        fp_rows: list[int] = []
        fp_cols: list[int] = []
        fp_values: list[float] = []
        for global_free, local_free in free_local.items():
            diagonal = 0.0
            for neighbor, weight in adjacency.get(global_free, {}).items():
                diagonal += weight
                if neighbor in free_set:
                    ff_rows.append(local_free)
                    ff_cols.append(free_local[neighbor])
                    ff_values.append(-weight)
                elif neighbor in prescribed_set:
                    fp_rows.append(local_free)
                    fp_cols.append(prescribed_local[neighbor])
                    fp_values.append(-weight)
                else:
                    raise ValueError(
                        "Free vertex "
                        f"{global_free} has neighbor {neighbor} that is neither "
                        "free nor prescribed; the prescribed set must contain "
                        "every graph neighbor of the free set (no stiffness leak)."
                    )
            ff_rows.append(local_free)
            ff_cols.append(local_free)
            ff_values.append(diagonal)

        num_free = free_ids.size
        num_prescribed = prescribed_ids.size
        l_ff = sp.csc_matrix(
            (ff_values, (ff_rows, ff_cols)),
            shape=(num_free, num_free),
        )
        l_fp = sp.csr_matrix(
            (fp_values, (fp_rows, fp_cols)),
            shape=(num_free, num_prescribed),
        )
        return AssembledSystem(
            free_ids=free_ids,
            prescribed_ids=prescribed_ids,
            factor=factorize_spd(l_ff),
            coupling=l_fp,
        )


class CorotationalMembraneAssembler:
    """Reference-frame CST membrane stiffness with weak 3D stabilization.

    Each original polygon is integrated as a centroid fan in a single local
    polygon frame.  The temporary centroid's two in-plane DOFs are statically
    condensed, so the original mesh and its DOF set are unchanged.  The
    resulting local membrane matrix is rotated into global 3D and assembled
    into one coupled system.

    A surface membrane has no bending stiffness: a triangulated flat sheet has
    exact out-of-plane hinge mechanisms, so a pure membrane ``K_ff`` is not
    generally SPD.  ``normal_stabilization`` adds an element-scaled ring-edge
    penalty on variation in each polygon's normal direction.  It removes those
    mechanisms and makes the linear first-milestone system coercive.
    """

    def __init__(
        self,
        *,
        poisson_ratio: float = 0.4,
        youngs_modulus: float = 1.0,
        thickness: float = 1.0,
        area_stiffening_exponent: float = 0.0,
        area_floor: float = 1e-12,
        normal_stabilization: float = 2e-2,
    ):
        poisson_ratio = float(poisson_ratio)
        if not (-1.0 < poisson_ratio < 0.5):
            raise ValueError("poisson_ratio must lie strictly between -1 and 0.5.")
        if float(youngs_modulus) <= 0.0:
            raise ValueError("youngs_modulus must be positive.")
        if float(thickness) <= 0.0:
            raise ValueError("thickness must be positive.")
        if float(area_stiffening_exponent) < 0.0:
            raise ValueError("area_stiffening_exponent must be non-negative.")
        if float(area_floor) <= 0.0:
            raise ValueError("area_floor must be positive.")
        if float(normal_stabilization) <= 0.0:
            raise ValueError(
                "normal_stabilization must be positive because a 3D surface "
                "membrane alone is not guaranteed to have an SPD free block."
            )
        self.poisson_ratio = poisson_ratio
        self.youngs_modulus = float(youngs_modulus)
        self.thickness = float(thickness)
        self.area_stiffening_exponent = float(area_stiffening_exponent)
        self.area_floor = float(area_floor)
        self.normal_stabilization = float(normal_stabilization)

    def assemble(
        self,
        mesh,
        *,
        free_ids: np.ndarray,
        prescribed_ids: np.ndarray,
        constrained_free_dofs: np.ndarray | None = None,
    ) -> CoupledAssembledSystem:
        mesh_data = _as_mesh_data(mesh)
        points = np.asarray(mesh_data.vertices, dtype=float).reshape((-1, 3))
        free_ids, prescribed_ids = _validate_partition(free_ids, prescribed_ids)
        free_local = {int(vertex): row for row, vertex in enumerate(free_ids)}
        prescribed_local = {
            int(vertex): row for row, vertex in enumerate(prescribed_ids)
        }
        free_set = set(free_local)
        prescribed_set = set(prescribed_local)

        ff_rows: list[np.ndarray] = []
        ff_cols: list[np.ndarray] = []
        ff_values: list[np.ndarray] = []
        fp_rows: list[np.ndarray] = []
        fp_cols: list[np.ndarray] = []
        fp_values: list[np.ndarray] = []

        for block in mesh_data.cell_blocks.values():
            cells = np.asarray(block, dtype=np.int64)
            if cells.ndim != 2 or cells.shape[1] < 3:
                continue
            for cell in cells:
                if not any(int(vertex) in free_set for vertex in cell):
                    continue
                missing = [
                    int(vertex)
                    for vertex in cell
                    if int(vertex) not in free_set
                    and int(vertex) not in prescribed_set
                ]
                if missing:
                    raise ValueError(
                        "A membrane element touching the free set contains "
                        f"unclassified vertices {missing[:10]}; use "
                        "element_neighbors(mesh, free_ids) for prescribed_ids."
                    )
                element = _polygon_membrane_stiffness(
                    points[cell],
                    poisson_ratio=self.poisson_ratio,
                    youngs_modulus=self.youngs_modulus,
                    thickness=self.thickness,
                    area_stiffening_exponent=self.area_stiffening_exponent,
                    area_floor=self.area_floor,
                    normal_stabilization=self.normal_stabilization,
                )
                _scatter_coupled_element(
                    cell,
                    element,
                    free_local=free_local,
                    prescribed_local=prescribed_local,
                    ff_rows=ff_rows,
                    ff_cols=ff_cols,
                    ff_values=ff_values,
                    fp_rows=fp_rows,
                    fp_cols=fp_cols,
                    fp_values=fp_values,
                )

        # The element-scaled normal term above supplies the physical
        # out-of-plane control.  Retain only a roundoff-scale isotropic graph
        # floor here so a pathological collection of local frames cannot leave
        # an exact algebraic null vector.
        for (vertex_a, vertex_b), weight in _edge_weights(
            mesh_data,
            points,
            stiffening_exponent=0.0,
            area_floor=self.area_floor,
        ).items():
            if vertex_a not in free_set and vertex_b not in free_set:
                continue
            value = 1e-10 * self.youngs_modulus * float(weight)
            for component in range(3):
                _scatter_edge_regularization(
                    vertex_a,
                    vertex_b,
                    component,
                    value,
                    free_local=free_local,
                    prescribed_local=prescribed_local,
                    ff_rows=ff_rows,
                    ff_cols=ff_cols,
                    ff_values=ff_values,
                    fp_rows=fp_rows,
                    fp_cols=fp_cols,
                    fp_values=fp_values,
                )

        num_free_dofs = 3 * free_ids.size
        num_prescribed_dofs = 3 * prescribed_ids.size
        k_ff = sp.coo_matrix(
            (
                np.concatenate(ff_values) if ff_values else np.empty(0),
                (
                    np.concatenate(ff_rows) if ff_rows else np.empty(0, dtype=np.int64),
                    np.concatenate(ff_cols) if ff_cols else np.empty(0, dtype=np.int64),
                ),
            ),
            shape=(num_free_dofs, num_free_dofs),
        ).tocsc()
        k_fp = sp.coo_matrix(
            (
                np.concatenate(fp_values) if fp_values else np.empty(0),
                (
                    np.concatenate(fp_rows) if fp_rows else np.empty(0, dtype=np.int64),
                    np.concatenate(fp_cols) if fp_cols else np.empty(0, dtype=np.int64),
                ),
            ),
            shape=(num_free_dofs, num_prescribed_dofs),
        ).tocsr()
        # Roundoff from local condensation can leave a tiny asymmetry.
        k_ff = (0.5 * (k_ff + k_ff.T)).tocsc()

        constrained = np.asarray(
            np.empty(0, dtype=np.int64)
            if constrained_free_dofs is None
            else constrained_free_dofs,
            dtype=np.int64,
        ).reshape(-1)
        if constrained.size:
            if np.any((constrained < 0) | (constrained >= num_free_dofs)):
                raise ValueError("constrained_free_dofs contains an invalid local DOF.")
            constrained = np.unique(constrained)
        active = np.setdiff1d(
            np.arange(num_free_dofs, dtype=np.int64),
            constrained,
            assume_unique=True,
        )
        if active.size == 0:
            raise ValueError("The membrane system has no active free DOFs.")
        scatter = sp.csr_matrix(
            (
                np.ones(active.size, dtype=float),
                (active, np.arange(active.size, dtype=np.int64)),
            ),
            shape=(num_free_dofs, active.size),
        )
        return CoupledAssembledSystem(
            free_ids=free_ids,
            prescribed_ids=prescribed_ids,
            active_free_dofs=active,
            factor=factorize_spd(k_ff[active][:, active]),
            coupling=k_fp[active],
            scatter=scatter,
        )


def graph_neighbors(
    mesh,
    vertex_ids: np.ndarray,
    *,
    include_quad_diagonals: bool = False,
    quad_bracing_mode: str | None = None,
) -> np.ndarray:
    """Return the mesh-graph neighbors of ``vertex_ids`` not in the set.

    Neighbors are defined by the ring edges of the triangle/quad cells.
    ``include_quad_diagonals`` retains the legacy request for both diagonals.
    ``quad_bracing_mode`` can instead select the single-diagonal,
    both-diagonal, or statically condensed virtual-center operator graph.  This
    is how the elastic prescribed set is grown from the free set: every
    stiffness neighbor of a free vertex must be prescribed so the free-free
    block has no stiffness leak.
    """

    mesh_data = _as_mesh_data(mesh)
    if quad_bracing_mode is not None:
        _validate_quad_bracing_mode(quad_bracing_mode)
    elif include_quad_diagonals:
        quad_bracing_mode = "both_diagonals"
    points = np.asarray(mesh_data.vertices, dtype=float)
    source = set(int(vertex) for vertex in np.asarray(vertex_ids, dtype=np.int64).reshape(-1))
    neighbors: set[int] = set()
    for block in mesh_data.cell_blocks.values():
        cells = np.asarray(block, dtype=np.int64)
        if cells.ndim != 2 or cells.shape[1] < 2:
            continue
        for cell in cells:
            ring = cell.tolist()
            count = len(ring)
            edges = [
                (ring[local_index], ring[(local_index + 1) % count])
                for local_index in range(count)
            ]
            if quad_bracing_mode is not None and count == 4:
                edges.extend(
                    (vertex_a, vertex_b)
                    for vertex_a, vertex_b, _ in _quad_brace_pairs(
                        points,
                        np.asarray(cell, dtype=np.int64),
                        mode=quad_bracing_mode,
                        weight=1.0,
                    )
                )
            for raw_a, raw_b in edges:
                vertex_a = int(raw_a)
                vertex_b = int(raw_b)
                if vertex_a == vertex_b:
                    continue
                if vertex_a in source and vertex_b not in source:
                    neighbors.add(vertex_b)
                elif vertex_b in source and vertex_a not in source:
                    neighbors.add(vertex_a)
    return np.array(sorted(neighbors), dtype=np.int64)


def element_neighbors(mesh, vertex_ids: np.ndarray) -> np.ndarray:
    """Return all co-element neighbors outside ``vertex_ids``.

    CST polygon integration produces coupling between every boundary vertex of
    a condensed polygon.  Its Dirichlet support therefore needs the complete
    one-element halo, not only the ring-edge halo used by the graph Laplacian.
    """

    mesh_data = _as_mesh_data(mesh)
    source = set(
        int(vertex)
        for vertex in np.asarray(vertex_ids, dtype=np.int64).reshape(-1)
    )
    neighbors: set[int] = set()
    for block in mesh_data.cell_blocks.values():
        cells = np.asarray(block, dtype=np.int64)
        if cells.ndim != 2 or cells.shape[1] < 3:
            continue
        for cell in cells:
            ring = [int(vertex) for vertex in cell]
            if any(vertex in source for vertex in ring):
                neighbors.update(vertex for vertex in ring if vertex not in source)
    return np.asarray(sorted(neighbors), dtype=np.int64)


def _validate_partition(
    free_ids: np.ndarray, prescribed_ids: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    free_ids = np.asarray(free_ids, dtype=np.int64).reshape(-1)
    prescribed_ids = np.asarray(prescribed_ids, dtype=np.int64).reshape(-1)
    if np.intersect1d(free_ids, prescribed_ids).size:
        raise ValueError("free_ids and prescribed_ids must be disjoint.")
    if np.unique(free_ids).size != free_ids.size:
        raise ValueError("free_ids must not contain duplicates.")
    if np.unique(prescribed_ids).size != prescribed_ids.size:
        raise ValueError("prescribed_ids must not contain duplicates.")
    return free_ids, prescribed_ids


def _polygon_membrane_stiffness(
    polygon: np.ndarray,
    *,
    poisson_ratio: float,
    youngs_modulus: float,
    thickness: float,
    area_stiffening_exponent: float,
    area_floor: float,
    normal_stabilization: float,
) -> np.ndarray:
    """Condensed centroid-fan CST stiffness for one original polygon."""

    polygon = np.asarray(polygon, dtype=float).reshape((-1, 3))
    count = polygon.shape[0]
    origin = np.mean(polygon, axis=0)
    normal = np.sum(np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0)
    normal_norm = float(np.linalg.norm(normal))
    if normal_norm <= area_floor:
        raise ValueError("Cannot assemble a membrane on a degenerate polygon.")
    normal /= normal_norm
    tangent_1 = polygon[1] - polygon[0]
    tangent_1 -= float(np.dot(tangent_1, normal)) * normal
    tangent_norm = float(np.linalg.norm(tangent_1))
    if tangent_norm <= area_floor:
        raise ValueError("Cannot construct a local frame for a degenerate polygon.")
    tangent_1 /= tangent_norm
    tangent_2 = np.cross(normal, tangent_1)
    basis = np.column_stack((tangent_1, tangent_2))
    coordinates = (polygon - origin) @ basis
    centroid = np.mean(coordinates, axis=0)

    plane_stress = youngs_modulus / (1.0 - poisson_ratio**2) * np.array(
        [
            [1.0, poisson_ratio, 0.0],
            [poisson_ratio, 1.0, 0.0],
            [0.0, 0.0, 0.5 * (1.0 - poisson_ratio)],
        ],
        dtype=float,
    )
    star = np.zeros((2 * (count + 1), 2 * (count + 1)), dtype=float)
    polygon_area = 0.0
    center_node = count
    for index in range(count):
        following = (index + 1) % count
        triangle = np.vstack((coordinates[index], coordinates[following], centroid))
        triangle_stiffness, area = _cst_stiffness(
            triangle,
            plane_stress=plane_stress,
            thickness=thickness,
        )
        polygon_area += area
        nodes = (index, following, center_node)
        dofs = np.asarray(
            [2 * node + component for node in nodes for component in range(2)],
            dtype=np.int64,
        )
        star[np.ix_(dofs, dofs)] += triangle_stiffness

    boundary_count = 2 * count
    k_bb = star[:boundary_count, :boundary_count]
    k_bc = star[:boundary_count, boundary_count:]
    k_cc = star[boundary_count:, boundary_count:]
    condensed = k_bb - k_bc @ np.linalg.solve(k_cc, k_bc.T)
    if area_stiffening_exponent:
        condensed *= max(polygon_area, area_floor) ** (-area_stiffening_exponent)

    transform = np.zeros((2 * count, 3 * count), dtype=float)
    for index in range(count):
        transform[2 * index : 2 * index + 2, 3 * index : 3 * index + 3] = basis.T
    global_stiffness = transform.T @ condensed @ transform
    # A membrane is blind to isometric hinge motion.  Penalize variation of the
    # correction in the polygon-normal direction, scaled by this element's own
    # membrane stiffness so highly graded CFD cells receive comparable control.
    membrane_scale = float(np.trace(global_stiffness)) / max(2 * count, 1)
    normal_projector = np.outer(normal, normal)
    for index in range(count):
        following = (index + 1) % count
        index_dofs = slice(3 * index, 3 * index + 3)
        following_dofs = slice(3 * following, 3 * following + 3)
        normal_block = normal_stabilization * membrane_scale * normal_projector
        global_stiffness[index_dofs, index_dofs] += normal_block
        global_stiffness[following_dofs, following_dofs] += normal_block
        global_stiffness[index_dofs, following_dofs] -= normal_block
        global_stiffness[following_dofs, index_dofs] -= normal_block
    return 0.5 * (global_stiffness + global_stiffness.T)


def _cst_stiffness(
    coordinates: np.ndarray,
    *,
    plane_stress: np.ndarray,
    thickness: float,
) -> tuple[np.ndarray, float]:
    x_1, y_1 = coordinates[0]
    x_2, y_2 = coordinates[1]
    x_3, y_3 = coordinates[2]
    twice_area = (x_2 - x_1) * (y_3 - y_1) - (x_3 - x_1) * (y_2 - y_1)
    if twice_area <= 0.0:
        raise ValueError("Polygon centroid fan contains a reversed CST triangle.")
    b = np.asarray((y_2 - y_3, y_3 - y_1, y_1 - y_2), dtype=float)
    c = np.asarray((x_3 - x_2, x_1 - x_3, x_2 - x_1), dtype=float)
    strain = np.zeros((3, 6), dtype=float)
    strain[0, 0::2] = b
    strain[1, 1::2] = c
    strain[2, 0::2] = c
    strain[2, 1::2] = b
    strain /= twice_area
    area = 0.5 * twice_area
    return thickness * area * (strain.T @ plane_stress @ strain), area


def _scatter_coupled_element(
    cell,
    stiffness,
    *,
    free_local,
    prescribed_local,
    ff_rows,
    ff_cols,
    ff_values,
    fp_rows,
    fp_cols,
    fp_values,
):
    free_element_dofs = []
    free_global_dofs = []
    prescribed_element_dofs = []
    prescribed_global_dofs = []
    for local_vertex, global_vertex in enumerate(cell):
        global_vertex = int(global_vertex)
        for component in range(3):
            element_dof = 3 * local_vertex + component
            if global_vertex in free_local:
                free_element_dofs.append(element_dof)
                free_global_dofs.append(3 * free_local[global_vertex] + component)
            else:
                prescribed_element_dofs.append(element_dof)
                prescribed_global_dofs.append(
                    3 * prescribed_local[global_vertex] + component
                )
    free_element_dofs = np.asarray(free_element_dofs, dtype=np.int64)
    free_global_dofs = np.asarray(free_global_dofs, dtype=np.int64)
    prescribed_element_dofs = np.asarray(prescribed_element_dofs, dtype=np.int64)
    prescribed_global_dofs = np.asarray(prescribed_global_dofs, dtype=np.int64)

    local_ff = stiffness[np.ix_(free_element_dofs, free_element_dofs)]
    ff_rows.append(np.repeat(free_global_dofs, free_global_dofs.size))
    ff_cols.append(np.tile(free_global_dofs, free_global_dofs.size))
    ff_values.append(local_ff.reshape(-1))
    if prescribed_global_dofs.size:
        local_fp = stiffness[np.ix_(free_element_dofs, prescribed_element_dofs)]
        fp_rows.append(np.repeat(free_global_dofs, prescribed_global_dofs.size))
        fp_cols.append(np.tile(prescribed_global_dofs, free_global_dofs.size))
        fp_values.append(local_fp.reshape(-1))


def _scatter_edge_regularization(
    vertex_a,
    vertex_b,
    component,
    weight,
    *,
    free_local,
    prescribed_local,
    ff_rows,
    ff_cols,
    ff_values,
    fp_rows,
    fp_cols,
    fp_values,
):
    for vertex, neighbor in ((vertex_a, vertex_b), (vertex_b, vertex_a)):
        if vertex not in free_local:
            continue
        row = 3 * free_local[vertex] + component
        ff_rows.append(np.asarray((row,), dtype=np.int64))
        ff_cols.append(np.asarray((row,), dtype=np.int64))
        ff_values.append(np.asarray((weight,), dtype=float))
        if neighbor in free_local:
            ff_rows.append(np.asarray((row,), dtype=np.int64))
            ff_cols.append(
                np.asarray((3 * free_local[neighbor] + component,), dtype=np.int64)
            )
            ff_values.append(np.asarray((-weight,), dtype=float))
        else:
            fp_rows.append(np.asarray((row,), dtype=np.int64))
            fp_cols.append(
                np.asarray(
                    (3 * prescribed_local[neighbor] + component,), dtype=np.int64
                )
            )
            fp_values.append(np.asarray((-weight,), dtype=float))


def _edge_weights(
    mesh_data,
    points: np.ndarray,
    *,
    stiffening_exponent: float,
    area_floor: float,
    quad_diagonal_weight: float = 0.0,
    quad_bracing_mode: str = "both_diagonals",
) -> dict[tuple[int, int], float]:
    """Reference-mesh edge weights keyed by ordered vertex pairs.

    Physical edges are the ring segments of every polygon.  For ``chi = 0``
    each physical edge weight is 1; for ``chi > 0`` each physical edge
    accumulates ``A_f^{-chi}`` from its incident faces.  With
    ``quad_diagonal_weight = lambda``, quads additionally contribute the
    selected auxiliary bracing operator.
    """

    uniform = stiffening_exponent == 0.0
    physical_weights: dict[tuple[int, int], float] = {}
    diagonal_weights: dict[tuple[int, int], float] = {}
    for block in mesh_data.cell_blocks.values():
        cells = np.asarray(block, dtype=np.int64)
        if cells.ndim != 2 or cells.shape[1] < 2:
            continue
        for cell in cells:
            if uniform:
                contribution = 1.0
            else:
                area = max(_polygon_area(points[cell]), area_floor)
                contribution = area ** (-stiffening_exponent)
            ring = cell.tolist()
            count = len(ring)
            for local_index in range(count):
                vertex_a = int(ring[local_index])
                vertex_b = int(ring[(local_index + 1) % count])
                if vertex_a == vertex_b:
                    continue
                key = (vertex_a, vertex_b) if vertex_a < vertex_b else (vertex_b, vertex_a)
                if uniform:
                    physical_weights[key] = 1.0
                else:
                    physical_weights[key] = (
                        physical_weights.get(key, 0.0) + contribution
                    )
            if len(ring) == 4 and quad_diagonal_weight > 0.0:
                for vertex_a, vertex_b, brace_scale in _quad_brace_pairs(
                    points,
                    np.asarray(cell, dtype=np.int64),
                    mode=quad_bracing_mode,
                    weight=quad_diagonal_weight,
                ):
                    if vertex_a == vertex_b:
                        continue
                    key = (
                        (vertex_a, vertex_b)
                        if vertex_a < vertex_b
                        else (vertex_b, vertex_a)
                    )
                    diagonal_weights[key] = (
                        diagonal_weights.get(key, 0.0)
                        + brace_scale * contribution
                    )
    weights = physical_weights.copy()
    for key, contribution in diagonal_weights.items():
        weights[key] = weights.get(key, 0.0) + contribution
    return weights


_QUAD_BRACING_MODES = (
    "single_diagonal",
    "both_diagonals",
    "virtual_center",
)


def _validate_quad_bracing_mode(mode: str) -> None:
    if str(mode) not in _QUAD_BRACING_MODES:
        choices = ", ".join(_QUAD_BRACING_MODES)
        raise ValueError(f"quad_bracing_mode must be one of: {choices}.")


def _quad_brace_pairs(
    points: np.ndarray,
    cell: np.ndarray,
    *,
    mode: str,
    weight: float,
) -> tuple[tuple[int, int, float], ...]:
    """Return condensed corner-pair contributions for one quad.

    ``single_diagonal`` selects the baseline diagonal that maximizes the worse
    mean-ratio quality of its two triangles.  ``both_diagonals`` contributes
    both crossing diagonals.  ``virtual_center`` represents four equal spokes
    of weight ``2 * weight`` to a free center node.  Eliminating that center
    exactly gives all six corner pairs weight ``weight / 2``.
    """

    _validate_quad_bracing_mode(mode)
    vertices = tuple(int(vertex) for vertex in np.asarray(cell).reshape(-1))
    if len(vertices) != 4 or weight == 0.0:
        return ()
    if mode == "single_diagonal":
        option_02 = min(
            _triangle_mean_ratio(points[[vertices[0], vertices[1], vertices[2]]]),
            _triangle_mean_ratio(points[[vertices[0], vertices[2], vertices[3]]]),
        )
        option_13 = min(
            _triangle_mean_ratio(points[[vertices[0], vertices[1], vertices[3]]]),
            _triangle_mean_ratio(points[[vertices[1], vertices[2], vertices[3]]]),
        )
        diagonal = (
            (vertices[0], vertices[2])
            if option_02 >= option_13
            else (vertices[1], vertices[3])
        )
        return ((diagonal[0], diagonal[1], 2.0 * weight),)
    if mode == "both_diagonals":
        return (
            (vertices[0], vertices[2], 2.0 * weight),
            (vertices[1], vertices[3], 2.0 * weight),
        )
    pair_scale = 0.5 * weight
    return tuple(
        (vertices[left], vertices[right], pair_scale)
        for left in range(4)
        for right in range(left + 1, 4)
    )


def _triangle_mean_ratio(triangle: np.ndarray) -> float:
    triangle = np.asarray(triangle, dtype=float).reshape((3, 3))
    edges = np.roll(triangle, -1, axis=0) - triangle
    squared_lengths = np.einsum("ij,ij->i", edges, edges)
    denominator = float(np.sum(squared_lengths))
    if denominator <= 1e-30:
        return 0.0
    twice_area = float(np.linalg.norm(np.cross(edges[0], -edges[2])))
    return 2.0 * np.sqrt(3.0) * twice_area / denominator


def _polygon_area(polygon: np.ndarray) -> float:
    polygon = np.asarray(polygon, dtype=float).reshape((-1, 3))
    normal = np.sum(np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0)
    return 0.5 * float(np.linalg.norm(normal))


__all__ = [
    "AssembledSystem",
    "CorotationalMembraneAssembler",
    "CoupledAssembledSystem",
    "GraphLaplacianAssembler",
    "StiffnessAssembler",
    "element_neighbors",
    "graph_neighbors",
]
