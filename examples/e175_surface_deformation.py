"""Deform an E175 CFD surface mesh with the differentiable mesh-motion pipeline.

The script walks the five stages the pipeline performs, in order:

1. **Choose geometry and mesh files.** A STEP body supplies the outer mould
   line; a surface mesh supplies the nodes that must follow it.
2. **Define design variables and component motion.** Each design variable is a
   differentiable control. Components declare how they respond, and
   ``connect`` names the closed intersection curves between them.
3. **Choose mesh-motion and quality settings.** Load stepping, seam-distance
   weighting, and polygon regularization for the graph-Laplacian solve.
4. **Run the differentiable mesh-motion model.** Intersections are recomputed,
   the interior is propagated, and every moved node is reprojected onto the
   deformed outer mould line.
5. **Inspect the result.** Fold, inversion, and quality diagnostics come back
   on the result object.

Run it directly::

    python examples/e175_surface_deformation.py

To deform the quad-dominant panel mesh instead, point ``SURFACE_MESH_FILE`` at
``QUAD_SURFACE_MESH_FILE``. Nothing else changes: the same positive
``PolygonRegularization`` weight applies to whichever cells the mesh has, and a
triangle-only surface simply has no polygon modes for it to constrain.
"""

from pathlib import Path
import tempfile

import csdl_alpha as csdl

import bsm3.mesh_motion as mm

ASSETS = (
    Path(__file__).resolve().parents[1]
    / "bsm3"
    / "core"
    / "boundary_surface_movement"
)
STEP_FILE = ASSETS / "embraer_175_no_winglets.stp"
SURFACE_MESH_FILE = (
    ASSETS
    / "fluent_R1_tet_euler_volume_mesh"
    / "e175_fluent_R1_aircraft_wall_tri.msh"
)
QUAD_SURFACE_MESH_FILE = (
    ASSETS / "embraer_175_quad_dominant_symmetric_no_winglets.msh"
)
CACHE_DIRECTORY = Path(tempfile.gettempdir()) / "bsm3_e175_example_cache"


def main(
    *,
    geometry_file: Path = STEP_FILE,
    surface_mesh_file: Path = SURFACE_MESH_FILE,
    cache_directory: Path = CACHE_DIRECTORY,
) -> mm.MeshMotionResult:
    """Deform the E175 surface mesh and report its quality.

    Parameters
    ----------
    geometry_file
        STEP body defining the outer mould line.
    surface_mesh_file
        Surface mesh whose nodes follow the deformed geometry.
    cache_directory
        Directory for reusable setup data. Reused runs are much faster.

    Returns
    -------
    mm.MeshMotionResult
        Differentiable coordinates plus forward diagnostics.
    """
    # 1. Choose geometry and mesh files
    inputs = mm.InputFiles(
        geometry_file=geometry_file,
        surface_mesh_file=surface_mesh_file,
        cache_directory=cache_directory,
    )

    # 2. Define design variables and component motion
    # The recorder is created, started, and stopped here: BSM3 never owns
    # global CSDL state, so this script composes inside a larger graph.
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    geometry = mm.GeometryModel()
    wing_shift = geometry.design_variable("wing_shift", 0.005)
    wing_incidence = geometry.design_variable("wing_incidence", 0.01)
    wing_area = geometry.design_variable("wing_area", 70.02)
    tail_incidence = geometry.design_variable("tail_incidence", 0.015)
    fuselage_width = geometry.design_variable("fuselage_width", 1.0002)

    geometry.add_lifting_surface(
        name="wing",
        search_name="wing",
        pivot_intersection="wing_root",
        translation_x=wing_shift,
        rotation_y_degrees=wing_incidence,
        area=wing_area,
        reference_area=70.0,
        reference_aspect_ratio=8.4,
    )
    geometry.add_lifting_surface(
        name="tail",
        search_name="HT",
        pivot_intersection="tail_root",
        rotation_y_degrees=tail_incidence,
        projection_name="horizontal_tail",
    )
    geometry.add_body(
        name="fuselage",
        search_name="fuselage",
        diameter_scale=fuselage_width,
    )
    geometry.connect(
        name="wing_root",
        driving_component="wing",
        query_component="fuselage",
    )
    geometry.connect(
        name="tail_root",
        driving_component="tail",
        query_component="fuselage",
    )

    # 3. Choose mesh-motion and quality settings
    motion = mm.MeshMotion(
        surface=mm.SurfaceMotion(
            load_steps=2,
            stiffening_exponent=1.5,
            distance_weighting=mm.DistanceWeighting(
                enabled=True,
                beta=5.0,
                length_scale=10.0,
                decay="exp",
            ),
            # Applies to whichever cells the mesh has. Triangles carry no
            # affine hourglass mode, so this is inactive on the tri wall and
            # active on the quad-dominant panel.
            polygon_regularization=mm.PolygonRegularization(weight=0.3),
        ),
        quality=mm.QualityChecks(surface=True),
        symmetry=True,
    )

    # 4. Run the differentiable mesh-motion model
    try:
        result = mm.run(
            inputs=inputs,
            geometry=geometry,
            motion=motion,
            recorder=recorder,
        )
    finally:
        recorder.stop()

    # 5. Inspect the result
    result.print_summary()
    return result


if __name__ == "__main__":
    main()
