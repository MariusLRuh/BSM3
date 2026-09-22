"""Mesh container, import, and export helpers for preprocessing workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class MeshData:
    """Raw surface mesh arrays used by preprocessing utilities.

    Parameters
    ----------
    vertices : ndarray of shape (n_vertices, 3)
        Cartesian vertex coordinates.
    connectivity : ndarray
        Flattened view of all element connectivities. This is a 2D integer
        array when all elements have the same width and an object array when
        mixed element widths are present.
    cell_types : ndarray of shape (n_elements,)
        Cell type label for each row in ``connectivity``.
    cell_blocks : dict[str, ndarray]
        Connectivity grouped by cell type, for example ``"triangle"`` or
        ``"quad"``. Indices are zero-based.
    node_ids : ndarray, optional
        Original one-based node IDs from the source file when available.
    element_ids : dict[str, ndarray], optional
        Original element IDs grouped by cell type when available.
    element_tags : dict[str, ndarray], optional
        Format-specific element tags grouped by cell type.
    metadata : dict, optional
        Reader/writer and preprocessing metadata.
    """

    vertices: np.ndarray
    connectivity: np.ndarray
    cell_types: np.ndarray
    cell_blocks: dict[str, np.ndarray]
    node_ids: np.ndarray | None = None
    element_ids: dict[str, np.ndarray] | None = None
    element_tags: dict[str, np.ndarray] | None = None
    metadata: dict[str, object] | None = None

    @property
    def nodes(self) -> np.ndarray:
        """Compatibility alias used by geometry and panel-method scripts."""
        return self.vertices

    @nodes.setter
    def nodes(self, value) -> None:
        self.vertices = np.asarray(value, dtype=float)


def import_mesh(mesh_file: str | Path) -> MeshData:
    """Read a supported mesh file.

    Parameters
    ----------
    mesh_file : str or Path
        Path to a Gmsh ``.msh`` or STL ``.stl`` mesh file.

    Returns
    -------
    MeshData
        Mesh vertices, connectivity blocks, and source metadata.

    Notes
    -----
    If ``meshio`` is installed, it is used for ``.msh`` files. Otherwise,
    ASCII Gmsh 2.x files are handled by the built-in parser.
    """
    path = Path(mesh_file)
    suffix = path.suffix.lower()
    if suffix == ".msh":
        from .gmsh import _import_msh

        return _import_msh(path)
    if suffix == ".stl":
        from .stl import _import_stl

        return _import_stl(path)
    raise ValueError(
        f"Unsupported mesh format {suffix!r}. Supported formats: "
        ".msh, .stl."
    )


def read_mesh(mesh_file: str | Path) -> MeshData:
    """Alias for :func:`import_mesh`."""
    return import_mesh(mesh_file)


def export_mesh(mesh, mesh_file: str | Path) -> None:
    """Write mesh data to disk.

    Parameters
    ----------
    mesh : MeshData or mesh-like
        Mesh object with ``vertices`` and ``cell_blocks``.
    mesh_file : str or Path
        Output path. Currently only Gmsh 2.2 ASCII ``.msh`` files are
        supported.
    """
    mesh_data = _as_mesh_data(mesh)
    path = Path(mesh_file)
    suffix = path.suffix.lower()
    if suffix != ".msh":
        raise ValueError(f"Unsupported export mesh format {suffix!r}. Supported formats: .msh.")
    from .gmsh import _write_gmsh_ascii

    _write_gmsh_ascii(mesh_data, path)


def _as_mesh_data(mesh) -> MeshData:
    if isinstance(mesh, MeshData):
        return mesh
    if isinstance(mesh, (str, Path)):
        return import_mesh(mesh)
    if hasattr(mesh, "vertices") and hasattr(mesh, "cell_blocks"):
        return _make_mesh_data(
            vertices=np.asarray(mesh.vertices, dtype=float),
            cell_blocks={
                str(cell_type): np.asarray(block, dtype=np.int64)
                for cell_type, block in mesh.cell_blocks.items()
            },
            node_ids=getattr(mesh, "node_ids", None),
            element_ids=getattr(mesh, "element_ids", None),
            element_tags=getattr(mesh, "element_tags", None),
            metadata=dict(getattr(mesh, "metadata", {}) or {}),
        )
    raise TypeError("mesh must be a MeshData object, MeshData-like object, or mesh file path.")


def import_trusted_polygon_pickle(mesh_file: str | Path) -> MeshData:
    """Read the trusted legacy polygon-surface dictionary format.

    Parameters
    ----------
    mesh_file : str or Path
        Pickle containing ``points`` and a sequence of variable-width
        ``connectivity`` rows. Because pickle can execute arbitrary code, this
        reader must only be used with trusted local assets.

    Returns
    -------
    MeshData
        Polygonal surface grouped into triangle, quad, and ``polygonN`` cell
        blocks without triangulating higher-order polygons.

    Raises
    ------
    ValueError
        If the stored points or connectivity do not describe a valid surface
        mesh.
    """
    import pickle

    path = Path(mesh_file)
    with path.open("rb") as stream:
        data = pickle.load(stream)
    if not isinstance(data, dict) or not {"points", "connectivity"} <= data.keys():
        raise ValueError(
            "A polygon pickle must contain 'points' and 'connectivity'."
        )

    vertices = np.asarray(data["points"], dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("Polygon-pickle points must have shape (n_vertices, 3).")

    cells = [
        np.asarray(cell, dtype=np.int64).reshape(-1)
        for cell in data["connectivity"]
    ]
    if not cells or any(cell.size < 3 for cell in cells):
        raise ValueError("Polygon-pickle cells must each contain at least 3 nodes.")
    if any(np.any(cell < 0) or np.any(cell >= vertices.shape[0]) for cell in cells):
        raise ValueError("Polygon-pickle connectivity contains an invalid node ID.")

    cell_blocks = {}
    sizes = np.asarray([cell.size for cell in cells], dtype=np.int64)
    for size in np.unique(sizes):
        cell_type = {3: "triangle", 4: "quad"}.get(
            int(size), f"polygon{int(size)}"
        )
        cell_blocks[cell_type] = np.asarray(
            [cell for cell in cells if cell.size == size],
            dtype=np.int64,
        )

    return _make_mesh_data(
        vertices=vertices,
        cell_blocks=cell_blocks,
        node_ids=None,
        element_ids=None,
        element_tags=None,
        metadata={"reader": "bsm3_polygon_pickle", "source": str(path)},
    )


def _make_mesh_data(
    *,
    vertices: np.ndarray,
    cell_blocks: dict[str, np.ndarray],
    node_ids: np.ndarray | None,
    element_ids: dict[str, np.ndarray] | None,
    element_tags: dict[str, np.ndarray] | None,
    metadata: dict[str, object],
) -> MeshData:
    # Keep the grouped cell blocks as the source of truth while also providing
    # a combined connectivity view for simple consumers.
    connectivity_parts = [
        np.asarray(block, dtype=np.int64)
        for block in cell_blocks.values()
    ]
    connectivity = _combine_connectivity(connectivity_parts)
    cell_types = np.concatenate(
        [
            np.full((block.shape[0],), cell_type, dtype=object)
            for cell_type, block in cell_blocks.items()
        ]
    )
    return MeshData(
        vertices=np.asarray(vertices, dtype=float),
        connectivity=connectivity,
        cell_types=cell_types,
        cell_blocks={
            cell_type: np.asarray(block, dtype=np.int64)
            for cell_type, block in cell_blocks.items()
        },
        node_ids=node_ids,
        element_ids=element_ids,
        element_tags=element_tags,
        metadata=metadata,
    )


def _combine_connectivity(connectivity_parts: list[np.ndarray]) -> np.ndarray:
    if not connectivity_parts:
        return np.empty((0, 0), dtype=np.int64)
    widths = {part.shape[1] for part in connectivity_parts}
    if len(widths) == 1:
        return np.vstack(connectivity_parts).astype(np.int64)

    cells = []
    for part in connectivity_parts:
        cells.extend(np.asarray(row, dtype=np.int64) for row in part)
    return np.asarray(cells, dtype=object)


def _merge_cell_blocks(blocks: dict[str, list[np.ndarray]]) -> dict[str, np.ndarray]:
    return {
        cell_type: np.vstack(cell_arrays).astype(np.int64)
        for cell_type, cell_arrays in blocks.items()
    }


def _array_from_variable_rows(rows: list[list[int]]) -> np.ndarray:
    if not rows:
        return np.empty((0, 0), dtype=np.int64)
    widths = {len(row) for row in rows}
    if len(widths) == 1:
        return np.asarray(rows, dtype=np.int64)
    return np.asarray([np.asarray(row, dtype=np.int64) for row in rows], dtype=object)
