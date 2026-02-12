import bpy
import gpu
import bmesh
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils
from mathutils import Vector
import math
import time

addon_keymaps = []

# --- PROPRIÉTÉS ET INTERFACE ---

class VIEW3D_PT_AntiTremblement(bpy.types.Panel):
    bl_label = "Softmove"
    bl_idname = "VIEW3D_PT_anti_tremblement"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SoftMove'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        wm = context.window_manager
        
        active = getattr(wm, "anti_tremble_active", False)
        
        col = layout.column(align=True)
        col.prop(scene, "anti_tremblement_radius", text="Rayon (Physique)")
        col.prop(scene, "anti_tremblement_offset", text="Offset (Sélection)")
        col.prop(scene, "anti_tremblement_sensitivity", text="Sensibilité")
        col.prop(scene, "anti_tremblement_friction", text="Friction (Cible)")
        col.prop(scene, "anti_tremblement_samples", text="Lissage (Frames)")
        
        layout.separator()
        
        # --- 3 COULEURS MAINTENANT ---
        col.prop(scene, "anti_tremble_color_cursor", text="Curseur (Orange)")
        col.prop(scene, "anti_tremble_color_line", text="Cercle (Trait)")
        col.prop(scene, "anti_tremble_color_select", text="Sélection (Mesh)")
        
        layout.separator()
        
        if active:
            layout.operator("view3d.anti_tremblement_toggle", text="Arrêter l'outil (F5)", icon='PAUSE', depress=True)
        else:
            layout.operator("view3d.anti_tremblement_toggle", text="Démarrer l'outil (F5)", icon='PLAY')

class OT_AntiTremblementToggle(bpy.types.Operator):
    bl_idname = "view3d.anti_tremblement_toggle"
    bl_label = "Toggle Anti Tremblement"

    def execute(self, context):
        wm = context.window_manager
        if getattr(wm, "anti_tremble_active", False):
            wm.anti_tremble_active = False
        else:
            bpy.ops.view3d.anti_tremblement_morph('INVOKE_DEFAULT')
        return {'FINISHED'}

class OT_AntiTremblementMorph(bpy.types.Operator):
    bl_idname = "view3d.anti_tremblement_morph"
    bl_label = "Anti Tremblement Morphing"

    def __init__(self):
        self.virtual_pos = Vector((0, 0)) 
        self.circle_pos = Vector((0, 0))
        self.handle = None
        self.first_run = True
        self.morph_data = [] 
        self.target_idx = -1
        self.target_obj = None
        self.current_mode = 'FACE'
        self.dynamic_sens = 1.0 
        self.last_mode = 'OBJECT' 
        self.mode_cooldown = 0.0
        self.mouse_history = [] 

    def draw_callback(self, context):
        try:
            scene = context.scene
            radius_phys = scene.anti_tremblement_radius
            radius_sel = max(1, radius_phys + scene.anti_tremblement_offset)
            
            # Récupération des 3 couleurs
            col_cursor = scene.anti_tremble_color_cursor
            col_line = scene.anti_tremble_color_line
            col_select = scene.anti_tremble_color_select # Nouvelle couleur
            
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            shader.bind()
            gpu.state.blend_set('ALPHA')
            
            # 1. Point Orange (Curseur virtuel)
            batch_pt = batch_for_shader(shader, 'POINTS', {"pos": [self.virtual_pos]})
            shader.uniform_float("color", (col_cursor[0], col_cursor[1], col_cursor[2], 1)) 
            gpu.state.point_size_set(7)
            batch_pt.draw(shader)

            # 2. Cercle Blanc (Fixe, physique)
            res = 32
            points_p = [(self.circle_pos[0] + math.cos(6.283*i/res)*radius_phys, 
                         self.circle_pos[1] + math.sin(6.283*i/res)*radius_phys) for i in range(res)]
            batch_p = batch_for_shader(shader, 'LINE_LOOP', {"pos": points_p})
            shader.uniform_float("color", (1, 1, 1, 0.2))
            gpu.state.line_width_set(1.5)
            batch_p.draw(shader)

            # 2b. Cercle de détection (Trait mouvant)
            points_s = [(self.circle_pos[0] + math.cos(6.283*i/res)*radius_sel, 
                         self.circle_pos[1] + math.sin(6.283*i/res)*radius_sel) for i in range(res)]
            batch_s = batch_for_shader(shader, 'LINE_LOOP', {"pos": points_s})
            # Utilise "Couleur Trait"
            shader.uniform_float("color", (col_line[0], col_line[1], col_line[2], 0.6))
            gpu.state.line_width_set(1.5)
            batch_s.draw(shader)

            # 3. Outline Sélection (Sur le mesh)
            if self.morph_data:
                draw_mode = 'LINE_LOOP' if self.current_mode == 'FACE' else 'LINES'
                if self.current_mode == 'VERT':
                    gpu.state.point_size_set(12)
                    draw_mode = 'POINTS'
                batch_morph = batch_for_shader(shader, draw_mode, {"pos": self.morph_data})
                
                # Utilise la NOUVELLE "Couleur Sélection"
                shader.uniform_float("color", (col_select[0], col_select[1], col_select[2], 1))
                gpu.state.line_width_set(4.0)
                batch_morph.draw(shader)
        except: pass

    def update_logic(self, context):
        current_time = time.time()
        if context.mode != self.last_mode:
            self.last_mode = context.mode
            self.mode_cooldown = current_time + 0.2
            self.morph_data = []
            self.target_obj = None
            return
        if current_time < self.mode_cooldown: return

        self.morph_data = []
        self.target_idx = -1
        radius_sel = max(1, context.scene.anti_tremblement_radius + context.scene.anti_tremblement_offset)
        
        sel_mode = context.tool_settings.mesh_select_mode
        self.current_mode = 'VERT' if sel_mode[0] else 'EDGE' if sel_mode[1] else 'FACE'
        region, rv3d = context.region, context.space_data.region_3d
        
        test_points = [self.circle_pos]
        for i in range(12):
            angle = (math.pi * 2 / 12) * i
            test_points.append(self.circle_pos + Vector((math.cos(angle), math.sin(angle))) * radius_sel)

        hit_data = []
        try:
            depsgraph = context.view_layer.depsgraph
            for pt in test_points:
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, pt)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, pt)
                hit, loc, norm, f_idx, h_obj, mat = context.scene.ray_cast(depsgraph, ray_origin, view_vector)
                if hit and h_obj.type == 'MESH':
                    hit_data.append((h_obj, f_idx))
                    break
        except: return

        if not hit_data:
            self.target_obj = None
            return

        self.target_obj, face_idx = hit_data[0]
        bm = None
        is_edit_mode = (self.target_obj.mode == 'EDIT')
        
        try:
            if is_edit_mode:
                bm = bmesh.from_edit_mesh(self.target_obj.data)
            else:
                bm = bmesh.new()
                bm.from_mesh(self.target_obj.data)
            
            bm.faces.ensure_lookup_table()
            if face_idx < len(bm.faces):
                matrix = self.target_obj.matrix_world
                if self.current_mode == 'VERT':
                    best_v = min(bm.faces[face_idx].verts, key=lambda v: (view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ v.co) - self.circle_pos).length)
                    p2d = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ best_v.co)
                    self.target_idx, self.morph_data = best_v.index, [(p2d.x, p2d.y)]
                elif self.current_mode == 'EDGE':
                    best_e = min(bm.faces[face_idx].edges, key=lambda e: (((view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ e.verts[0].co) + view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ e.verts[1].co))/2) - self.circle_pos).length)
                    v1 = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ best_e.verts[0].co)
                    v2 = view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ best_e.verts[1].co)
                    self.target_idx, self.morph_data = best_e.index, [(v1.x, v1.y), (v2.x, v2.y)]
                else:
                    self.target_idx = face_idx
                    self.morph_data = [(p.x, p.y) for v in bm.faces[face_idx].verts if (p := view3d_utils.location_3d_to_region_2d(region, rv3d, matrix @ v.co))]
        except:
            self.morph_data = []
            self.target_idx = -1
        finally:
            if bm and not is_edit_mode: bm.free()

    def stop_modal(self, context):
        if self.handle:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
        context.window.cursor_set('DEFAULT')
        context.window_manager.anti_tremble_active = False 
        if context.area: context.area.tag_redraw()

    def modal(self, context, event):
        if not getattr(context.window_manager, "anti_tremble_active", False):
            self.stop_modal(context)
            return {'FINISHED'}

        context.area.tag_redraw()

        is_over_ui = False
        area = context.area
        if not (area.x <= event.mouse_x <= area.x + area.width and 
                area.y <= event.mouse_y <= area.y + area.height):
            is_over_ui = True
        
        if not is_over_ui:
            for region in area.regions:
                if region.type != 'WINDOW': 
                    if (region.x <= event.mouse_x <= region.x + region.width) and \
                       (region.y <= event.mouse_y <= region.y + region.height):
                        is_over_ui = True
                        break
        
        if is_over_ui:
            context.window.cursor_set('DEFAULT')
            self.mouse_history = [] 
            try:
                current_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
                self.virtual_pos = current_mouse.copy()
                self.circle_pos = current_mouse.copy()
            except: pass
            return {'PASS_THROUGH'}
        else:
            context.window.cursor_set('NONE')

        if event.value == 'PRESS' and event.type not in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE'}:
            if event.type == 'F5':
                return {'PASS_THROUGH'}
            return {'PASS_THROUGH'}

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}:
            return {'PASS_THROUGH'}

        if event.type == 'ESC':
            self.stop_modal(context)
            return {'CANCELLED'}

        self.update_logic(context)

        if event.type == 'MOUSEMOVE':
            raw_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            
            if self.first_run:
                self.virtual_pos, self.circle_pos = raw_mouse.copy(), raw_mouse.copy()
                self.mouse_history = [raw_mouse.copy()] * context.scene.anti_tremblement_samples
                self.first_run = False
            
            self.mouse_history.append(raw_mouse)
            samples = context.scene.anti_tremblement_samples
            if len(self.mouse_history) > samples:
                self.mouse_history.pop(0)
            
            if self.mouse_history:
                avg_x = sum(p.x for p in self.mouse_history) / len(self.mouse_history)
                avg_y = sum(p.y for p in self.mouse_history) / len(self.mouse_history)
                target_pos = Vector((avg_x, avg_y))
            else:
                target_pos = raw_mouse

            delta = target_pos - self.virtual_pos 
            
            if delta.length > 300: 
                self.virtual_pos = target_pos 
                self.mouse_history = [target_pos] * samples 
                return {'PASS_THROUGH'}

            sens = context.scene.anti_tremblement_sensitivity
            if self.target_idx != -1: sens *= context.scene.anti_tremblement_friction
            
            self.dynamic_sens += (sens - self.dynamic_sens) * 0.2
            self.virtual_pos += delta * self.dynamic_sens
            
            win_x = int(self.virtual_pos.x) + (event.mouse_x - event.mouse_region_x)
            win_y = int(self.virtual_pos.y) + (event.mouse_y - event.mouse_region_y)
            context.window.cursor_warp(win_x, win_y)

            diff = self.virtual_pos - self.circle_pos
            if diff.length > context.scene.anti_tremblement_radius:
                self.circle_pos += diff.normalized() * (diff.length - context.scene.anti_tremblement_radius)
            
            self.circle_pos += (self.virtual_pos - self.circle_pos) * 0.05
            
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if time.time() < self.mode_cooldown: return {'PASS_THROUGH'}
            if self.target_obj and self.target_idx != -1:
                try:
                    if context.mode == 'EDIT_MESH':
                        bm = bmesh.from_edit_mesh(self.target_obj.data)
                        if not event.shift: bpy.ops.mesh.select_all(action='DESELECT')
                        if self.current_mode == 'VERT': 
                            bm.verts.ensure_lookup_table()
                            bm.verts[self.target_idx].select = True
                        elif self.current_mode == 'EDGE': 
                            bm.edges.ensure_lookup_table()
                            bm.edges[self.target_idx].select = True
                        else: 
                            bm.faces.ensure_lookup_table()
                            bm.faces[self.target_idx].select = True
                        bmesh.update_edit_mesh(self.target_obj.data)
                    else:
                        if not event.shift: bpy.ops.object.select_all(action='DESELECT')
                        self.target_obj.select_set(True)
                        context.view_layer.objects.active = self.target_obj
                except: pass
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            context.window_manager.anti_tremble_active = True
            self.handle = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL')
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return {'CANCELLED'}

# --- REGISTRATION ---

classes = (
    VIEW3D_PT_AntiTremblement,
    OT_AntiTremblementMorph,
    OT_AntiTremblementToggle,
)

def register():
    bpy.types.Scene.anti_tremblement_radius = bpy.props.IntProperty(name="Rayon", default=30, min=5, max=300)
    bpy.types.Scene.anti_tremblement_offset = bpy.props.IntProperty(name="Offset", default=-20, min=-100, max=100)
    bpy.types.Scene.anti_tremblement_sensitivity = bpy.props.FloatProperty(name="Sensibilité", default=1.0, min=0.01, max=1.0)
    bpy.types.Scene.anti_tremblement_friction = bpy.props.FloatProperty(name="Friction", default=0.75, min=0.01, max=1.0)
    bpy.types.Scene.anti_tremblement_samples = bpy.props.IntProperty(name="Lissage (Frames)", default=8, min=1, max=50)
    
    # --- 3 COULEURS ---
    bpy.types.Scene.anti_tremble_color_cursor = bpy.props.FloatVectorProperty(
        name="Couleur Curseur", subtype='COLOR', default=(1.0, 0.5, 0.0), min=0.0, max=1.0, size=3
    )
    bpy.types.Scene.anti_tremble_color_line = bpy.props.FloatVectorProperty(
        name="Couleur Trait", subtype='COLOR', default=(0.0, 0.6, 1.0), min=0.0, max=1.0, size=3
    )
    bpy.types.Scene.anti_tremble_color_select = bpy.props.FloatVectorProperty(
        name="Couleur Sélection", subtype='COLOR', default=(0.0, 1.0, 1.0), min=0.0, max=1.0, size=3
    )
    
    bpy.types.WindowManager.anti_tremble_active = bpy.props.BoolProperty(default=False)
    
    for cls in classes:
        bpy.utils.register_class(cls)
        
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("view3d.anti_tremblement_toggle", 'F5', 'PRESS')
        addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.anti_tremblement_radius
    del bpy.types.Scene.anti_tremblement_offset
    del bpy.types.Scene.anti_tremblement_sensitivity
    del bpy.types.Scene.anti_tremblement_friction
    del bpy.types.Scene.anti_tremblement_samples
    del bpy.types.Scene.anti_tremble_color_cursor
    del bpy.types.Scene.anti_tremble_color_line
    del bpy.types.Scene.anti_tremble_color_select # Nettoyage
    del bpy.types.WindowManager.anti_tremble_active

if __name__ == "__main__":
    register()