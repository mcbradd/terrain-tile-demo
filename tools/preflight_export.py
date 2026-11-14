"""PF-02 Blender-side script: export the default cube with the exact call of SPEC 11.5."""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
cube = bpy.data.objects["Cube"]
bpy.ops.object.select_all(action="DESELECT")
cube.select_set(True)
bpy.context.view_layer.objects.active = cube
bpy.ops.export_scene.gltf(
    filepath=out, check_existing=False, export_format='GLB',
    use_selection=True, export_apply=True, export_yup=True,
    export_texcoords=False, export_normals=True, export_tangents=False,
    export_materials='EXPORT', export_vertex_color='NONE',
    export_cameras=False, export_lights=False, export_animations=False,
    export_skins=False, export_morph=False, export_extras=False,
    export_draco_mesh_compression_enable=False,
    export_meshopt_compression_enable=False,
    export_use_gltfpack=False, will_save_settings=False)
sys.exit(0)
