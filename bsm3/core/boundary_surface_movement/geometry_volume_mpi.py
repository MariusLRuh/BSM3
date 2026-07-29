"""MPI communication helpers for the rank-0 geometry-to-volume operation.

The geometry, projection, surface-motion, and volume-motion pipeline is
expensive and is executed only on MPI rank 0.  Its deformed global volume
coordinates are then broadcast so that the distributed DAFoam backend on every
rank can extract its local OpenFOAM partition.  This module centralizes the
small set of collectives that the forward and reverse operations need, with two
properties that matter for correctness and testability:

* ``mpi4py`` is imported lazily.  Importing BSM3, running the dependency-free
  unit tests, and single-process execution therefore do not require an MPI
  build.  When ``mpi4py`` is unavailable (or no communicator is supplied), a
  :class:`SerialComm` provides the identity behaviour of a one-rank world.
* Every collective is wrapped so that a rank-0 exception is broadcast *before*
  any bulk data transfer.  This prevents the classic deadlock where rank 0
  raises while the other ranks block inside a matching collective.

The typed array collectives (:func:`broadcast_array`, :func:`reduce_gradient`)
use the buffer protocol (``Bcast``/``Reduce``/``Allreduce``) rather than the
pickled object collectives, as required for the large coordinate arrays.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Communicator resolution and serial fallback
# ---------------------------------------------------------------------------
class SerialComm:
    """A minimal single-rank stand-in for an MPI communicator.

    Only the subset of the ``mpi4py`` interface used by the geometry-to-volume
    operation is implemented, with the semantics of a one-process world: every
    broadcast is the identity, every reduction returns its own contribution, and
    every gather/scatter is a one-element list.  It lets the forward/reverse
    machinery and its tests run unchanged without an MPI build.
    """

    def __init__(self, rank: int = 0, size: int = 1):
        if size != 1 or rank != 0:
            raise ValueError(
                "SerialComm models a single-rank world; use a real MPI "
                "communicator for multi-rank execution."
            )
        self.rank = 0
        self.size = 1

    # Pickled object collectives ------------------------------------------------
    def bcast(self, obj: Any, root: int = 0) -> Any:
        return obj

    def gather(self, obj: Any, root: int = 0) -> list[Any]:
        return [obj]

    def scatter(self, sequence: Optional[list[Any]], root: int = 0) -> Any:
        if sequence is None:
            return None
        return sequence[0]

    def allgather(self, obj: Any) -> list[Any]:
        return [obj]

    # Typed buffer collectives --------------------------------------------------
    def Bcast(self, buffer: np.ndarray, root: int = 0) -> None:
        return None

    def Reduce(self, sendbuf: np.ndarray, recvbuf: np.ndarray, op=None, root: int = 0) -> None:
        recvbuf[...] = np.asarray(sendbuf)

    def Allreduce(self, sendbuf: np.ndarray, recvbuf: np.ndarray, op=None) -> None:
        recvbuf[...] = np.asarray(sendbuf)

    def Barrier(self) -> None:
        return None


def resolve_comm(comm: Any = None) -> Any:
    """Return a usable communicator.

    If ``comm`` is provided it is returned unchanged.  Otherwise the real
    ``MPI.COMM_WORLD`` is used when ``mpi4py`` is importable, and a
    :class:`SerialComm` is returned when it is not.
    """

    if comm is not None:
        return comm
    try:
        from mpi4py import MPI
    except ImportError:
        return SerialComm()
    return MPI.COMM_WORLD


def comm_rank(comm: Any) -> int:
    return int(getattr(comm, "rank", 0))


def comm_size(comm: Any) -> int:
    return int(getattr(comm, "size", 1))


def is_root(comm: Any, root: int = 0) -> bool:
    return comm_rank(comm) == root


# ---------------------------------------------------------------------------
# Collective exception propagation
# ---------------------------------------------------------------------------
def run_on_root(
    comm: Any,
    function: Callable[[], Any],
    *,
    root: int = 0,
) -> Any:
    """Run ``function`` on ``root`` and propagate any exception to all ranks.

    The root rank runs ``function`` inside a try/except and reduces the outcome
    to an error string.  That string is broadcast (pickled ``bcast`` of a small
    object) to every rank *before* any bulk data movement, so a root failure
    raises :class:`RuntimeError` symmetrically on all ranks instead of leaving
    non-root ranks blocked in a later collective.  Non-root ranks always return
    ``None``.
    """

    error_message: Optional[str] = None
    result: Any = None
    if is_root(comm, root):
        try:
            result = function()
        except Exception as error:  # noqa: BLE001 - re-raised on all ranks
            error_message = f"{type(error).__name__}: {error}"
    error_message = comm.bcast(error_message, root=root)
    if error_message is not None:
        raise RuntimeError(error_message)
    return result


# ---------------------------------------------------------------------------
# Typed array collectives
# ---------------------------------------------------------------------------
def broadcast_array(
    comm: Any,
    array: Optional[np.ndarray],
    *,
    shape: tuple[int, ...],
    dtype=np.float64,
    root: int = 0,
) -> np.ndarray:
    """Broadcast a dense, contiguous array from ``root`` to every rank.

    On the root rank ``array`` must already hold the data with the declared
    ``shape``/``dtype``; on non-root ranks it may be ``None`` and is allocated
    here.  A typed ``MPI.Bcast`` is used (not the pickled ``bcast``) so the
    large coordinate array moves through the buffer protocol.
    """

    if is_root(comm, root):
        if array is None:
            raise ValueError("Root rank must supply the array to broadcast.")
        buffer = np.ascontiguousarray(np.asarray(array, dtype=dtype))
        if buffer.shape != tuple(shape):
            raise ValueError(
                f"Root array shape {buffer.shape} does not match the declared "
                f"broadcast shape {tuple(shape)}."
            )
    else:
        buffer = np.empty(shape, dtype=dtype)
    if comm_size(comm) > 1:
        comm.Bcast(buffer, root=root)
    return buffer


def extract_local_coordinates(
    global_coordinates: np.ndarray,
    local_to_global: np.ndarray,
) -> np.ndarray:
    """Forward scatter: pick each rank's local points from the global array.

    ``local = global[local_to_global]``.  Processor-boundary points may appear
    on several ranks; this is the forward operator ``S`` whose exact transpose
    ``S^T`` is :func:`assemble_local_gradient` (scatter-add).  The pair must
    satisfy ``<S x, ybar> == <x, S^T ybar>``; see
    ``test_forward_scatter_and_reverse_add_are_transposes``.
    """

    global_array = np.asarray(global_coordinates, dtype=np.float64)
    if global_array.ndim != 2 or global_array.shape[1] != 3:
        raise ValueError("global_coordinates must have shape (n_global, 3).")
    return global_array[np.asarray(local_to_global)]


def assemble_local_gradient(
    local_gradient: np.ndarray,
    local_to_global: np.ndarray,
    num_global_points: int,
) -> np.ndarray:
    """Scatter-add a local per-point gradient into a dense global-order buffer.

    This is the exact transpose ``S^T`` of :func:`extract_local_coordinates`.
    ``np.add.at`` is required (not fancy-index assignment) because
    processor-boundary points are duplicated across partitions and legitimately
    map several local rows to the same global point; their contributions must
    add rather than overwrite.  Forward overwrite and reverse duplication would
    *not* be a transpose pair.
    """

    local = np.asarray(local_gradient, dtype=np.float64)
    if local.ndim != 2 or local.shape[1] != 3:
        raise ValueError("local_gradient must have shape (n_local, 3).")
    if local.shape[0] != np.asarray(local_to_global).size:
        raise ValueError(
            "local_gradient rows must match the length of local_to_global."
        )
    global_gradient = np.zeros((int(num_global_points), 3), dtype=np.float64)
    np.add.at(global_gradient, np.asarray(local_to_global), local)
    return global_gradient


def reduce_gradient(
    comm: Any,
    local_global_gradient: np.ndarray,
    *,
    ownership: str = "root",
    root: int = 0,
) -> np.ndarray:
    """Sum per-rank dense global-order gradients across the communicator.

    ``ownership='root'`` uses ``MPI.Reduce`` so only ``root`` owns the assembled
    result (non-root ranks receive zeros); ``ownership='replicated'`` uses
    ``MPI.Allreduce`` so every rank holds an identical copy.  The two are
    numerically equivalent on the root rank and are validated against each other
    during the first MPI validation stage.
    """

    if ownership not in ("root", "replicated"):
        raise ValueError("ownership must be 'root' or 'replicated'.")
    contribution = np.ascontiguousarray(
        np.asarray(local_global_gradient, dtype=np.float64)
    )
    if comm_size(comm) == 1:
        return contribution.copy()

    # Real MPI needs a concrete reduction op; mock communicators used in the
    # dependency-free tests ignore it, so tolerate mpi4py being absent.
    try:
        from mpi4py import MPI

        sum_op = MPI.SUM
    except ImportError:
        sum_op = None

    reduced = np.zeros_like(contribution)
    if ownership == "replicated":
        comm.Allreduce(contribution, reduced, op=sum_op)
        return reduced
    comm.Reduce(contribution, reduced, op=sum_op, root=root)
    if is_root(comm, root):
        return reduced
    return np.zeros_like(contribution)


def verify_replicated_values(
    comm: Any,
    array: np.ndarray,
    *,
    name: str,
    absolute_tolerance: float = 0.0,
) -> None:
    """Assert that ``array`` is identical on every rank.

    Used in debug mode to catch silent divergence of the replicated design
    variables before rank 0 uses its own copy.  A no-op in a one-rank world.
    """

    if comm_size(comm) == 1:
        return
    reference = comm.bcast(
        np.asarray(array, dtype=np.float64).copy() if is_root(comm) else None,
        root=0,
    )
    local = np.asarray(array, dtype=np.float64)
    if local.shape != reference.shape:
        raise RuntimeError(
            f"Replicated array {name!r} has shape {local.shape} on rank "
            f"{comm_rank(comm)} but {reference.shape} on rank 0."
        )
    worst = float(np.max(np.abs(local - reference))) if local.size else 0.0
    if worst > absolute_tolerance:
        raise RuntimeError(
            f"Replicated array {name!r} differs across ranks by {worst:.3e} "
            f"on rank {comm_rank(comm)} (tolerance {absolute_tolerance:.3e})."
        )


__all__ = [
    "SerialComm",
    "resolve_comm",
    "comm_rank",
    "comm_size",
    "is_root",
    "run_on_root",
    "broadcast_array",
    "extract_local_coordinates",
    "assemble_local_gradient",
    "reduce_gradient",
    "verify_replicated_values",
]
