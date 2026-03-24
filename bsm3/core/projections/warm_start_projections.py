"""
pyvista_warmstart.py

Build a per-patch structured triangulation from B-spline surface samples (with (patch_id,u,v)
stored per vertex), then use PyVista's batched closest-cell query to produce warm-start
Newton seeds (patch_id, u0, v0) via barycentric interpolation.

Key guarantees:
- Triangles never bridge patches (triangulate per patch only).
- Every mesh vertex carries (patch_id, u, v).
- Closest-point-on-triangulation gives you a robust broad-phase; barycentric interpolation
  yields an excellent parametric warm-start for Newton on the underlying surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import jax
import jax.numpy as jnp
import numpy as np
import pyvista as pv
import pickle
from pathlib import Path


DEFAULT_FUN_SET_PATH = Path(__file__).with_name("refitted_fun_set.pkl")

# ----------------------------
# Mesh construction
# ----------------------------

def _structured_tri_faces(Nu: int, Nv: int, vertex_offset: int) -> np.ndarray:
    """
    Returns faces in PyVista "faces" format: a flat array of [3, i0, i1, i2, 3, ...]
    for a Nu x Nv structured grid (two triangles per quad cell).

    Vertex indexing: idx(j,k) = vertex_offset + j*Nv + k
    """
    if Nu < 2 or Nv < 2:
        raise ValueError("Need Nu>=2 and Nv>=2 to form triangles.")

    # Quad cells: (j,k) for j=0..Nu-2, k=0..Nv-2
    j = np.arange(Nu - 1)[:, None]
    k = np.arange(Nv - 1)[None, :]
    j = np.broadcast_to(j, (Nu - 1, Nv - 1)).ravel()
    k = np.broadcast_to(k, (Nu - 1, Nv - 1)).ravel()

    v00 = vertex_offset + j * Nv + k
    v10 = vertex_offset + (j + 1) * Nv + k
    v11 = vertex_offset + (j + 1) * Nv + (k + 1)
    v01 = vertex_offset + j * Nv + (k + 1)

    # Two triangles per quad: (v00,v10,v11) and (v00,v11,v01)
    tris = np.stack(
        [
            np.stack([v00, v10, v11], axis=1),
            np.stack([v00, v11, v01], axis=1),
        ],
        axis=1,
    ).reshape(-1, 3)  # (2*(Nu-1)*(Nv-1), 3)

    faces = np.empty((tris.shape[0], 4), dtype=np.int64)
    faces[:, 0] = 3
    faces[:, 1:] = tris
    return faces.ravel()


def build_sampled_patches_mesh(
    function_set,
    patch_indices: Iterable[int],
    Nu: int,
    Nv: int,
    u_range: Tuple[float, float] = (0.0, 1.0),
    v_range: Tuple[float, float] = (0.0, 1.0),
) -> pv.PolyData:
    """
    Samples each patch on a structured (Nu x Nv) parametric grid and triangulates *per patch*.
    Stores per-vertex:
      - patch_id (int)
      - u (float)
      - v (float)

    Assumes your API:
      function_set.evaluate(parametric_coordinates=(i, uv))
    where uv is (M,2) and returns (M,3).

    Returns a single merged PolyData containing all patches (but with no cross-patch triangles).
    """
    patch_indices = list(patch_indices)

    u = np.linspace(u_range[0], u_range[1], Nu, dtype=np.float64)
    v = np.linspace(v_range[0], v_range[1], Nv, dtype=np.float64)
    UU, VV = np.meshgrid(u, v, indexing="ij")         # (Nu,Nv)
    uv = np.stack([UU.ravel(), VV.ravel()], axis=1)   # (Nu*Nv, 2)


    all_pts: List[np.ndarray] = []
    all_faces: List[np.ndarray] = []
    all_patch_id: List[np.ndarray] = []
    all_u: List[np.ndarray] = []
    all_v: List[np.ndarray] = []

    offset = 0
    for i in patch_indices:
        parametric_coordinates = [(i, uv_pt) for uv_pt in uv]
        xyz = function_set.evaluate(parametric_coordinates=parametric_coordinates, non_csdl=True)  # (Nu*Nv,3)
        xyz = np.asarray(xyz, dtype=np.float64).reshape(-1, 3)  # (Nu*Nv,3)

        all_pts.append(xyz)
        all_faces.append(_structured_tri_faces(Nu, Nv, vertex_offset=offset))

        all_patch_id.append(np.full((xyz.shape[0],), int(i), dtype=np.int32))
        all_u.append(uv[:, 0].copy())
        all_v.append(uv[:, 1].copy())

        offset += xyz.shape[0]

    pts = np.vstack(all_pts)
    faces = np.concatenate(all_faces)

    mesh = pv.PolyData(pts, faces)
    mesh.point_data["patch_id"] = np.concatenate(all_patch_id)
    mesh.point_data["u"] = np.concatenate(all_u).astype(np.float64)
    mesh.point_data["v"] = np.concatenate(all_v).astype(np.float64)
    return mesh


# ----------------------------
# Closest-cell warm start
# ----------------------------

def _faces_to_tris(mesh: pv.PolyData) -> np.ndarray:
    """
    Returns triangle vertex indices as (T,3) int64 array.
    Assumes mesh is pure triangles.
    """
    f = np.asarray(mesh.faces, dtype=np.int64)
    f = f.reshape(-1, 4)
    if not np.all(f[:, 0] == 3):
        raise ValueError("Mesh contains non-triangle faces. Expected pure triangles.")
    return f[:, 1:4]


def _barycentric_coords_batch(
    p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray, eps: float = 1e-14
) -> np.ndarray:
    """
    Vectorized barycentric coordinates for many points:
      p,a,b,c are (N,3). Returns w as (N,3) with rows [w0,w1,w2].

    Robust fallback for degenerate triangles: pick nearest vertex weights.
    """
    v0 = b - a
    v1 = c - a
    v2 = p - a

    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("ij,ij->i", v2, v0)
    d21 = np.einsum("ij,ij->i", v2, v1)

    denom = d00 * d11 - d01 * d01
    ok = np.abs(denom) > eps

    w = np.empty((p.shape[0], 3), dtype=np.float64)

    # normal case
    v = np.zeros_like(denom)
    w2 = np.zeros_like(denom)
    v[ok] = (d11[ok] * d20[ok] - d01[ok] * d21[ok]) / denom[ok]
    w2[ok] = (d00[ok] * d21[ok] - d01[ok] * d20[ok]) / denom[ok]
    u = 1.0 - v - w2
    w[ok, 0] = u[ok]
    w[ok, 1] = v[ok]
    w[ok, 2] = w2[ok]

    # degenerate fallback: nearest vertex
    if np.any(~ok):
        idx = np.where(~ok)[0]
        pa = p[idx] - a[idx]
        pb = p[idx] - b[idx]
        pc = p[idx] - c[idx]
        da = np.einsum("ij,ij->i", pa, pa)
        db = np.einsum("ij,ij->i", pb, pb)
        dc = np.einsum("ij,ij->i", pc, pc)
        which = np.argmin(np.stack([da, db, dc], axis=1), axis=1)

        w[idx] = 0.0
        w[idx, which] = 1.0

    return w


@dataclass(frozen=True)
class WarmStartResult:
    patch_id: np.ndarray     # (N,) int32
    uv0: np.ndarray          # (N,2) float64
    closest_pts: np.ndarray  # (N,3) float64
    cell_ids: np.ndarray     # (N,) int64
    dist2: np.ndarray        # (N,) float64


def warm_start_from_triangulation(
    mesh: pv.PolyData,
    points: np.ndarray,
) -> WarmStartResult:
    """
    Batched closest-cell query + barycentric interpolation of (u,v).

    Returns:
      patch_id[i], uv0[i] as Newton seed for projecting points[i] onto patch patch_id[i].
    """
    points = np.asarray(points, dtype=np.float64)

    # Batched closest triangle + closest point (C++ loop inside VTK)
    cell_ids, closest_pts = mesh.find_closest_cell(points, return_closest_point=True)
    cell_ids = np.asarray(cell_ids, dtype=np.int64)
    closest_pts = np.asarray(closest_pts, dtype=np.float64)

    # Gather triangle vertices for each selected cell
    tris = _faces_to_tris(mesh)              # (T,3)
    tri_vids = tris[cell_ids]               # (N,3)

    xyz = np.asarray(mesh.points, dtype=np.float64)  # (V,3)
    a = xyz[tri_vids[:, 0]]
    b = xyz[tri_vids[:, 1]]
    c = xyz[tri_vids[:, 2]]

    w = _barycentric_coords_batch(closest_pts, a, b, c)  # (N,3)

    # Per-vertex (patch_id,u,v)
    patch_v = np.asarray(mesh.point_data["patch_id"], dtype=np.int32)
    u_v = np.asarray(mesh.point_data["u"], dtype=np.float64)
    v_v = np.asarray(mesh.point_data["v"], dtype=np.float64)

    pid0 = patch_v[tri_vids[:, 0]]
    pid1 = patch_v[tri_vids[:, 1]]
    pid2 = patch_v[tri_vids[:, 2]]

    # Sanity: should be identical due to per-patch triangulation
    same = (pid0 == pid1) & (pid0 == pid2)
    if not np.all(same):
        bad = np.where(~same)[0][:10]
        raise RuntimeError(
            f"Found triangles bridging patches. First offenders indices: {bad}. "
            f"Fix by triangulating per patch only (structured grid connectivity)."
        )

    u0 = w[:, 0] * u_v[tri_vids[:, 0]] + w[:, 1] * u_v[tri_vids[:, 1]] + w[:, 2] * u_v[tri_vids[:, 2]]
    v0 = w[:, 0] * v_v[tri_vids[:, 0]] + w[:, 1] * v_v[tri_vids[:, 1]] + w[:, 2] * v_v[tri_vids[:, 2]]

    uv0 = np.stack([u0, v0], axis=1)

    diff = points - closest_pts
    dist2 = np.einsum("ij,ij->i", diff, diff)

    return WarmStartResult(
        patch_id=pid0,
        uv0=uv0,
        closest_pts=closest_pts,
        cell_ids=cell_ids,
        dist2=dist2,
    )


# ----------------------------
# Optional: edge-aware multi-seeding
# ----------------------------

EdgeName = str  # "u0", "u1", "v0", "v1"

@dataclass(frozen=True)
class NeighborEdgeMap:
    """
    Maps (patch_id, edge) -> (neighbor_patch_id, neighbor_edge, reverse_param)

    reverse_param means: along the shared edge, swap orientation:
      - for u-edges, "along edge" parameter is v
      - for v-edges, "along edge" parameter is u
    """
    neighbor_patch: int
    neighbor_edge: EdgeName
    reverse_along_edge: bool = False


def _which_edge(u: float, v: float, eps: float) -> List[EdgeName]:
    edges = []
    if u <= eps: edges.append("u0")
    if u >= 1.0 - eps: edges.append("u1")
    if v <= eps: edges.append("v0")
    if v >= 1.0 - eps: edges.append("v1")
    return edges


def _map_uv_across_edge(
    uv: np.ndarray,
    from_edge: EdgeName,
    to_edge: EdgeName,
    reverse_along_edge: bool,
) -> np.ndarray:
    """
    Map a param coordinate on one patch edge to the corresponding coordinate on the neighbor edge.

    Convention:
      - Edge "u0": u=0, along-edge coordinate is v
      - Edge "u1": u=1, along-edge coordinate is v
      - Edge "v0": v=0, along-edge coordinate is u
      - Edge "v1": v=1, along-edge coordinate is u
    """
    u, v = float(uv[0]), float(uv[1])

    if from_edge in ("u0", "u1"):
        t = v
        if reverse_along_edge:
            t = 1.0 - t
        # place on to_edge
        if to_edge == "u0": return np.array([0.0, t])
        if to_edge == "u1": return np.array([1.0, t])
        if to_edge == "v0": return np.array([t, 0.0])
        if to_edge == "v1": return np.array([t, 1.0])
    else:
        t = u
        if reverse_along_edge:
            t = 1.0 - t
        if to_edge == "u0": return np.array([0.0, t])
        if to_edge == "u1": return np.array([1.0, t])
        if to_edge == "v0": return np.array([t, 0.0])
        if to_edge == "v1": return np.array([t, 1.0])

    raise ValueError(f"Invalid edge mapping: {from_edge} -> {to_edge}")


def generate_edge_neighbor_seeds(
    patch_id: np.ndarray,
    uv0: np.ndarray,
    edge_map: Dict[Tuple[int, EdgeName], NeighborEdgeMap],
    eps_edge: float = 1e-3,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Given primary seeds (patch_id, uv0), generate additional seeds across neighboring patches
    when uv0 is near an edge.

    Returns a list of (patch_id_all, uv_all) candidate sets.
    - First entry is the original seeds.
    - Subsequent entries are neighbor seeds (same length N), but with patch_id set to neighbor
      where an edge match exists; otherwise keeps original seed.

    Typical usage:
      candidates = generate_edge_neighbor_seeds(...)
      run Newton for each candidate set; pick best result per point.
    """
    patch_id = np.asarray(patch_id, dtype=np.int32)
    uv0 = np.asarray(uv0, dtype=np.float64)

    candidates: List[Tuple[np.ndarray, np.ndarray]] = [(patch_id.copy(), uv0.copy())]

    # For each point, collect all edges it is near
    N = uv0.shape[0]
    neighbor_sets: Dict[Tuple[int, EdgeName], Tuple[np.ndarray, np.ndarray]] = {}

    for i in range(N):
        pid = int(patch_id[i])
        u, v = float(uv0[i, 0]), float(uv0[i, 1])
        near = _which_edge(u, v, eps_edge)
        for e in near:
            key = (pid, e)
            if key not in edge_map:
                continue
            # Create candidate set for this (pid,e) if not exists
            if key not in neighbor_sets:
                neighbor_sets[key] = (patch_id.copy(), uv0.copy())

            pid_c, uv_c = neighbor_sets[key]
            nbr = edge_map[key]
            pid_c[i] = int(nbr.neighbor_patch)
            uv_c[i] = _map_uv_across_edge(uv0[i], e, nbr.neighbor_edge, nbr.reverse_along_edge)

    candidates.extend(list(neighbor_sets.values()))
    return candidates


# ----------------------------
# Example glue for Newton
# ----------------------------

def pick_best_newton_result(
    points: np.ndarray,
    candidates: List[Tuple[np.ndarray, np.ndarray]],
    newton_project_fn,
):
    """
    Runs your Newton projector for each candidate seed set and selects best per point.

    newton_project_fn signature should be something like:
      xproj, uv, dist2 = newton_project_fn(points, patch_id, uv0)
    with batch support.

    Returns best (xproj, patch_id, uv, dist2).
    """
    points = np.asarray(points, dtype=np.float64)
    N = points.shape[0]

    best_dist2 = np.full((N,), np.inf, dtype=np.float64)
    best_x = np.zeros((N, 3), dtype=np.float64)
    best_pid = np.zeros((N,), dtype=np.int32)
    best_uv = np.zeros((N, 2), dtype=np.float64)

    for pid, uv0 in candidates:
        xproj, uv, dist2 = newton_project_fn(points, pid, uv0)  # user-provided
        dist2 = np.asarray(dist2, dtype=np.float64)

        mask = dist2 < best_dist2
        best_dist2[mask] = dist2[mask]
        best_x[mask] = xproj[mask]
        best_pid[mask] = pid[mask]
        best_uv[mask] = uv[mask]

    return best_x, best_pid, best_uv, best_dist2

def sample_bounding_box_faces(bbox_min, bbox_max, num_samples_per_face=10):
    x_min_face = np.random.uniform(bbox_min[1], bbox_max[1], num_samples_per_face)
    y_min_face = np.random.uniform(bbox_min[2], bbox_max[2], num_samples_per_face)
    z_min_face = np.random.uniform(bbox_min[0], bbox_max[0], num_samples_per_face)
    
    # zy face front
    x_zy_front = bbox_min[0]
    y_zy_front_left = bbox_min[1]
    y_zy_front_right = bbox_max[1]
    z_zy_front_bottom = bbox_min[2]
    z_zy_front_top = bbox_max[2]
    
    interp_points_zy_front_bottom = np.linspace(
        np.array([x_zy_front, y_zy_front_left, z_zy_front_bottom]),
        np.array([x_zy_front, y_zy_front_right, z_zy_front_bottom]),
        int(num_samples_per_face**0.5),
    )
    interp_points_zy_front_left = np.linspace(
        np.array([x_zy_front, y_zy_front_left, z_zy_front_bottom]),
        np.array([x_zy_front, y_zy_front_left, z_zy_front_top]),
        int(num_samples_per_face**0.5),
    )

    # tensor product to get grid points on the face
    grid_points_zy_front = []
    for i in range(int(num_samples_per_face**0.5)):
        for j in range(int(num_samples_per_face**0.5)):
            grid_points_zy_front.append([
                x_zy_front,
                interp_points_zy_front_bottom[i, 1],
                interp_points_zy_front_left[j, 2],
            ])
    grid_points_zy_front = np.array(grid_points_zy_front)
    
    # zy face back
    grid_points_zy_back = grid_points_zy_front.copy()
    grid_points_zy_back[:, 0] = bbox_max[0]

    grid_points_zy = np.vstack([grid_points_zy_front, grid_points_zy_back])


    # xy face top
    x_xy_top = np.linspace(bbox_min[0], bbox_max[0], int(num_samples_per_face**0.5))
    y_xy_top = np.linspace(bbox_min[1], bbox_max[1], int(num_samples_per_face**0.5))
    z_xy_top = bbox_max[2]
    grid_points_xy_top = []
    for i in range(int(num_samples_per_face**0.5)):
        for j in range(int(num_samples_per_face**0.5)):
            grid_points_xy_top.append([
                x_xy_top[i],
                y_xy_top[j],
                z_xy_top,
            ])
    grid_points_xy_top = np.array(grid_points_xy_top)

    # xy face bottom
    grid_points_xy_bottom = grid_points_xy_top.copy()
    grid_points_xy_bottom[:, 2] = bbox_min[2]

    grid_points_zy = np.vstack([grid_points_zy, grid_points_xy_top, grid_points_xy_bottom])

    # xz face left
    y_xz_left = bbox_min[1]
    x_xz_left = np.linspace(bbox_min[0], bbox_max[0], int(num_samples_per_face**0.5))
    z_xz_left = np.linspace(bbox_min[2], bbox_max[2], int(num_samples_per_face**0.5))
    grid_points_xz_left = []
    for i in range(int(num_samples_per_face**0.5)):
        for j in range(int(num_samples_per_face**0.5)):
            grid_points_xz_left.append([
                x_xz_left[i],
                y_xz_left,
                z_xz_left[j],
            ])
    grid_points_xz_left = np.array(grid_points_xz_left)

    # xz face right
    grid_points_xz_right = grid_points_xz_left.copy()
    grid_points_xz_right[:, 1] = bbox_max[1]

    grid_points_zy = np.vstack([grid_points_zy, grid_points_xz_left, grid_points_xz_right])

    return grid_points_zy


def sort_by_patch(patch_id: np.ndarray, *arrays):
    """
    Sorts patch_id and any number of aligned arrays (same first dimension) by patch_id.

    Returns:
      order: permutation indices
      inv_order: inverse permutation
      patch_id_sorted, *arrays_sorted
    """
    patch_id = np.asarray(patch_id)
    order = np.argsort(patch_id, kind="stable")
    inv_order = np.empty_like(order)
    inv_order[order] = np.arange(order.size, dtype=order.dtype)

    out = [patch_id[order]]
    for a in arrays:
        a = np.asarray(a)
        if a.shape[0] != patch_id.shape[0]:
            raise ValueError("All arrays must have same length as patch_id.")
        out.append(a[order])

    return order, inv_order, *out

def unsort(inv_order: np.ndarray, *arrays_sorted):
    """
    Applies inverse permutation to bring arrays back to original order.
    """
    return [np.asarray(a)[inv_order] for a in arrays_sorted]


def load_function_set(pickle_path) -> lfs.FunctionSet:
    with open(pickle_path, "rb") as f:
        wing_fun_set_data = pickle.load(f)

    functions: Dict[int, lfs.Function] = {}
    for key, fun_data in wing_fun_set_data.items():
        b_spline_space = lfs.BSplineSpaceNew(
            num_parametric_dimensions=2,
            degree=fun_data["degree"],
            coefficients_shape=fun_data["coefficients_shape"],
        )
        functions[int(key)] = lfs.Function(
            space=b_spline_space,
            coefficients=fun_data["coefficients"],
        )

    return lfs.FunctionSet(functions=functions)


if __name__ == "__main__":
    import lsdo_function_spaces as lfs
    import csdl_alpha as csdl
    import numpy as np
    import pyvista as pv
    from gauss_newton_projection import project_points_gauss_newton_numpy   
    from lsdo_function_spaces.core.spaces.non_cython_bsplines.b_spline_patch_projection_optimized import project_points_lm_numpy 
    
    jax.config.update("jax_enable_x64", True)
    jax.log_compiles(True)

    recorder = csdl.Recorder(inline=True)
    recorder.start()

    file_path = 'bsm3/core/projections/'
    file_name = 'swept_wing.stp'
    lpc = lfs.import_file_patched(file_path + file_name, parallelize=False)
    # lpc = load_function_set(pickle_path=DEFAULT_FUN_SET_PATH)
    
    # Create bounding box for lpc geom
    coefficients = []
    for fn_ind, fun in lpc.functions.items():
        ctrl = np.asarray(fun.coefficients.value)  # (nu,nv,3)
        coefficients.append(ctrl.reshape(-1, 3))
    all_ctrl = np.vstack(coefficients)
    ctrl_plot = lfs.plot_points(points=all_ctrl, color='red', show=False)
    # lpc.plot(additional_plotting_elements=[ctrl_plot], show=True, opacity=0.5)
    # exit()
    bbox_min = all_ctrl.min(axis=0)
    bbox_max = all_ctrl.max(axis=0)
    bbox_min_max = np.vstack([bbox_min, bbox_max])

    print("BBox min:", bbox_min)
    print("BBox max:", bbox_max)
    
    # add small buffer to bbox
    buffer = 0.1 * (bbox_max - bbox_min)
    bbox_min -= buffer
    bbox_max += buffer

    # sample points of bbox surfaces
    num_samples_per_face = 10000
    bbox_points = sample_bounding_box_faces(bbox_min, bbox_max, num_samples_per_face)
    print("number of bbox points:", bbox_points.shape[0])

    num_patches = len(lpc.functions)
    print(f"Imported {num_patches} patches.")

    # 1) Build sampled mesh from your B-spline surface set
    mesh = build_sampled_patches_mesh(
        function_set=lpc,
        patch_indices=range(num_patches),
        Nu=200,
        Nv=200,
    )

    # 2) Warm-start seed from PyVista batched projection
    warm = warm_start_from_triangulation(
        mesh=mesh,
        points=bbox_points,
    )

    patch_id = warm.patch_id
    uv0 = warm.uv0
    closest_pts = warm.closest_pts

    # order, inv_order, patch_id_sorted, uv0_sorted, points_sorted = sort_by_patch(patch_id, uv0, bbox_points)
    order, inv_order, patch_id_sorted, uv0_sorted, bbox_points_sorted = sort_by_patch(
        patch_id, uv0, bbox_points
    )

    # assemble per-patch [(patch_id  array[v0 | points_sorted])]
    warm_start_data = []
    start_index = 0
    for i in np.unique(patch_id_sorted):
        count_i = np.sum(patch_id_sorted == i)
        stop_index = start_index + count_i
        data_i = np.zeros((count_i, 5), dtype=np.float64)
        data_i[:, 0:2] = uv0_sorted[start_index:stop_index]
        data_i[:, 2:5] = bbox_points_sorted[start_index:stop_index]
        warm_start_data.append((int(i), data_i))
        start_index = stop_index

    projection_results = []
    for patch_i, data_i in warm_start_data:
        print(f"Processing patch {patch_i} with {data_i.shape[0]} points.")
        fun = lpc.functions[patch_i]
        coefficients = np.asarray(fun.coefficients.value) 
        knots = fun.space.knots
        degrees = fun.space.degree
        num_parametric_dims = fun.space.num_parametric_dimensions

        points_in_space = np.array(data_i[:, 2:5])  # (M,3)
        nearest_para_points = np.array(data_i[:, 0:2])  # (

        # batched_projection = jax.jit(jax.vmap(
        #         lambda pt, u0, cps: compute_point_to_bspline_projection(
        #             point=pt,
        #             degrees=degrees,
        #             coefficients=cps,
        #             para_coords=u0,
        #             # knots=tuple([jnp.array(knot_vectors_i) for knot_vectors_i in knots]),
        #             knots=tuple([tuple(knot_vectors_i.tolist()) for knot_vectors_i in knots]),
        #         ), in_axes=(0, 0, None)
        #     ))

        # batched_projection = make_projector_lm_jax(
        #     degrees, knots, 
        # )

        # para, res, converged, final_i, J, _, _ = batched_projection(
        # para, converged = batched_projection(
        #     points_in_space, 
        #     nearest_para_points,
        #     coefficients,
        # )
        para, converged, _, residual, num_iter = project_points_gauss_newton_numpy(
            points_in_space,
            nearest_para_points,
            coefficients,
            degrees,
            knots,
        )

        para = np.array(para).reshape(-1, num_parametric_dims)
        
        id_para_combo = [(patch_i, para[j]) for j in range(para.shape[0])]
        projection_results.append(id_para_combo)

        if not converged.all():
            print(f"Warning: {np.sum(~converged)} out of {len(converged)} projection points did not converge.")
            print(f"  Max residual: {np.max(residual)}")
            print(f"  Max iterations: {np.max(num_iter)}")
            # print("Initial guess for these points was:", nearest_para_points[~converged])
            # print("Final parameter coordinates for these points were:", para[~converged])
            # print("Final residuals for these points were:", residual[~converged])
            # print("Final iteration counts for these points were:", final_i[~converged])
            # print("Jacobian for these points was:", J[~converged])

        else:
            print(f"All {len(converged)} projection points converged successfully.")
            # print(f"  Average iterations: {np.mean(final_i)}")
            print(f"  Max residual: {np.max(residual)}; Max iterations: {np.max(num_iter)}")

    # apply inverse sort to get back to original order
    projection_results = [item for sublist in projection_results for item in sublist]
    projection_results_ordered = [projection_results[inv_ord] for inv_ord in inv_order]

    print("Number of projected points:", len(projection_results_ordered))
    
    # evaluate to verify
    proj_eval = lpc.evaluate(parametric_coordinates=projection_results_ordered, non_csdl=True, plot=False)

    # compare to closest pts
    proj_eval = np.asarray(proj_eval, dtype=np.float64).reshape(-1, 3)
    diff = closest_pts - proj_eval
    
    # plot bbox points, closest pts, projected pts and draw arrows
    p = pv.Plotter()
    p.add_mesh(mesh, color="lightgray", opacity=0.8, show_edges=True)
    p.add_points(bbox_points, color="red", point_size=10, render_points_as_spheres=True)
    p.add_points(closest_pts, color="blue", point_size=8, render_points_as_spheres=True)
    p.add_points(proj_eval, color="green", point_size=6, render_points_as_spheres=True)
    # Arrow appearance controls (length multiplier and radii for shaft/tip)
    arrow_scale = 1.0           # multiply arrow length by this
    arrow_shaft_radius = 0.01  # thickness of the arrow shaft
    arrow_tip_radius = 0.01     # radius of the arrow tip
    arrow_tip_length = 0.1      # fraction of the arrow length occupied by the tip
    
    test_para_coords = [(int(patch_id[i]), uv0[i]) for i in range(bbox_points.shape[0])]
    test_proj_pts = lpc.evaluate(parametric_coordinates=test_para_coords, non_csdl=True)
    test_proj_pts = np.asarray(test_proj_pts, dtype=np.float64).reshape(-1, 3)
    proj_diff = closest_pts - test_proj_pts

    proj_diff_norm = np.linalg.norm(proj_diff, axis=1)
    # print("max proj diff norm:", np.max(proj_diff_norm))
    # exit()

    proj_dist2 = np.einsum("ij,ij->i", proj_diff, proj_diff)
    print("Max projection error after warm start (should be small):", np.sqrt(np.max(proj_dist2)))

    p = pv.Plotter()
    p.add_mesh(mesh, color="lightgray", opacity=0.5, show_edges=True)
    p.add_points(bbox_points, color="red", point_size=10, render_points_as_spheres=True)
    p.add_points(closest_pts, color="blue", point_size=8, render_points_as_spheres=True)
    p.show()




    