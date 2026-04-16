# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import bpy
from bpy_extras import anim_utils
from bpy.types import Action, ActionSlot, Context, Object, PoseBone
from .bl_logger import logger
# from .progress_bar import (
#     init_progress,
#     update_progress,
#     finish_progress,
# )

BLENDER_5_0_OR_LATER = bpy.app.version >= (5, 0, 0)


@dataclass(frozen=True)
class ActionAssignment:
    """An action/slot pair that should be converted for an armature."""
    action: Action
    slot: Optional[ActionSlot]
    label: str


def get_bone_select(pose_bone: PoseBone) -> bool:
    """Get selection state of a bone for either Blender 4.5 or 5.0+"""
    if BLENDER_5_0_OR_LATER:
        return pose_bone.select
    else:
        return pose_bone.bone.select


def set_bone_select(pose_bone: PoseBone, value: bool) -> None:
    """Set selection state of a bone for either Blender 4.5 or 5.0+"""
    if BLENDER_5_0_OR_LATER:
        pose_bone.select = value
    else:
        pose_bone.bone.select = value


def dprint(message: str) -> None:
    """Prints in the system console if the addon's developer printing is ON"""
    prefs = bpy.context.preferences.addons[__package__].preferences
    if prefs.developer_print:
        # print(f"[Convert Rot Mode]: {message}")
        logger.debug(message)


def get_list_frames_from_action(
    action: Optional[Action],
    slot: Optional[ActionSlot]
) -> List[float]:
    """
    Return the frames that contain rotation keyframes for an action slot.
    """
    list_frames: List[float] = []

    if action is None or slot is None:
        return list_frames

    if BLENDER_5_0_OR_LATER:
        bag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
    else:
        bag = anim_utils.action_get_channelbag_for_slot(action, slot)
        if bag is None:
            return list_frames

    fcurves = bag.fcurves

    for curve in fcurves:
        # skip non-rotation curves
        if "rotation" not in curve.data_path:
            continue

        keyframe_points = curve.keyframe_points

        for keyframe in keyframe_points:
            frame = keyframe.co[0]
            if frame not in list_frames:
                list_frames.append(frame)

    return sorted(list_frames)


def get_list_frames(bone: PoseBone) -> List[float]:
    """Return frames with rotation keyframes on the armature's active action."""
    armature = bone.id_data
    ad = armature.animation_data

    if ad is None or ad.action is None:
        return []

    return get_list_frames_from_action(ad.action, ad.action_slot)


def iter_nla_strips(strips: Iterable[Any]) -> Iterable[Any]:
    """Yield NLA strips recursively so meta strips are also covered."""
    for strip in strips:
        yield strip
        child_strips = getattr(strip, "strips", None)
        if child_strips is not None and len(child_strips) > 0:
            yield from iter_nla_strips(child_strips)


def collect_armature_action_assignments(armature: Object) -> List[ActionAssignment]:
    """Collect unique actions that are attached to an armature."""
    ad = armature.animation_data
    if ad is None:
        return []

    assignments: List[ActionAssignment] = []
    seen = set()

    def add_assignment(
        action: Optional[Action],
        slot: Optional[ActionSlot],
        label: str
    ) -> None:
        if action is None:
            return

        key = (
            action.name_full,
            slot.identifier if slot is not None else "",
        )
        if key in seen:
            return

        seen.add(key)
        assignments.append(ActionAssignment(action, slot, label))

    add_assignment(ad.action, ad.action_slot, "active action")

    for track in ad.nla_tracks:
        for strip in iter_nla_strips(track.strips):
            add_assignment(
                getattr(strip, "action", None),
                getattr(strip, "action_slot", None),
                f"NLA strip '{strip.name}'",
            )

    return assignments


def store_armature_animation_state(armature: Object) -> Dict[str, Any]:
    """Capture the armature animation state so it can be restored later."""
    ad = armature.animation_data
    if ad is None:
        return {}

    return {
        "action": ad.action,
        "action_slot": ad.action_slot,
        "use_nla": ad.use_nla,
    }


def restore_armature_animation_state(
    armature: Object,
    state: Dict[str, Any]
) -> None:
    """Restore the armature animation state after conversion."""
    ad = armature.animation_data
    if ad is None or not state:
        return

    ad.use_nla = state["use_nla"]
    ad.action = state["action"]

    stored_slot = state["action_slot"]
    if stored_slot is not None and ad.action is not None:
        try:
            ad.action_slot = stored_slot
        except Exception as exc:
            dprint(f"Unable to restore action slot: {exc}")

    bpy.context.scene.frame_set(bpy.context.scene.frame_current)


def activate_armature_action_assignment(
    armature: Object,
    assignment: ActionAssignment
) -> None:
    """Make an action assignment the active source for conversion."""
    ad = armature.animation_data
    if ad is None:
        raise RuntimeError("Armature has no animation data to activate.")

    ad.use_nla = False
    ad.action = assignment.action

    if assignment.slot is not None:
        try:
            ad.action_slot = assignment.slot
        except Exception as exc:
            raise RuntimeError(
                f"Unable to activate slot for '{assignment.action.name}': {exc}"
            ) from exc

    bpy.context.scene.frame_set(bpy.context.scene.frame_current)


def deselect_all_bones() -> None:
    """Deselect all bones"""
    for bone in bpy.context.selected_pose_bones:
        set_bone_select(bone, False)


def get_rotation_locks(bone: PoseBone) -> List[bool]:
    """Return the current rotation lock state of the bone as a list."""
    return list(bone.lock_rotation) + [
        bone.lock_rotation_w,
        bone.lock_rotations_4d,
    ]


def jump_next_frame(context: Context) -> None:
    """
    Jump to the next frame in the timeline.
    Also jumps back and forth to force refresh the values for
    'Copy Global Transforms' to work properly when copying.
    """
    bpy.ops.screen.keyframe_jump(next=True)
    context.scene.frame_current += 1
    context.scene.frame_current -= 1


def toggle_rotation_locks(
    bone: PoseBone,
    mode: str,
    locks: Optional[List[bool]] = None
) -> None:

    """Toggle the rotation locks of a bone."""
    if mode == 'OFF':
        bone.lock_rotation[0] = False
        bone.lock_rotation[1] = False
        bone.lock_rotation[2] = False
        bone.lock_rotation_w = False
        bone.lock_rotations_4d = False
    elif mode == 'ON' and locks:
        bone.lock_rotation[0] = locks[0]
        bone.lock_rotation[1] = locks[1]
        bone.lock_rotation[2] = locks[2]
        bone.lock_rotation_w = locks[3]
        bone.lock_rotations_4d = locks[4]


def setup_bone_for_conversion(context: Context, bone: PoseBone) -> None:
    """Make only a specified bone selected and active before conversion"""
    deselect_all_bones()
    # Use bone.bone to avoid ArmatureBones.active expects a Bone, not PoseBone
    context.object.data.bones.active = bone.bone
    set_bone_select(bone, True)
    logger.debug(f"### Working on bone '{bone.name}' ###")


def prepare_bone_locks(bone: PoseBone) -> Optional[List[bool]]:
    """Store and remove rotation locks for a bone before conversion."""
    preserve_locks = bpy.context.scene.CRM_Properties.preserveLocks

    if preserve_locks:
        locks = get_rotation_locks(bone)
        toggle_rotation_locks(bone, 'OFF')
        dprint(" |  # Backed up and unlocked rotations")
        return locks
    else:
        toggle_rotation_locks(bone, 'OFF')
        dprint(" |  # Unlocked rotations")
        return None


def setup_initial_keyframe(bone: PoseBone, first_frame: float) -> str:
    """
    Jump at the start frame and place a keyframe to make sure no unwanted
    changes in animation happen from there to the next keyframe.
    Returns the original rotation mode.
    """
    original_rmode = bone.rotation_mode
    scene = bpy.context.scene
    scene.frame_set(int(first_frame))
    # bpy.ops.screen.frame_jump(end=False)
    bone.rotation_mode = original_rmode
    bone.keyframe_insert(
        "rotation_mode",
        frame=int(first_frame),
        group=bone.name
    )
    return original_rmode


def convert_frame_rotation(context: Context, bone: PoseBone, original_rmode: str) -> None:
    """Convert rotation mode for a single frame."""
    target_rmode = context.scene.CRM_Properties.targetRmode
    current_frame = context.scene.frame_current
    bone_name = bone.name

    logger.debug(f" # Frame {current_frame}")

    # Set to original rmode, keyframe it, then refresh values by setting current frame
    # Must refresh AFTER keyframing, otherwise the it just ignores the rotation mode change after first keyframe
    # Tried with context.view_layer.update() but it didn't work
    bone.rotation_mode = original_rmode
    bone.keyframe_insert("rotation_mode", frame=current_frame, group=bone_name)
    context.scene.frame_set(current_frame)
    logger.debug(f" |  # '{bone_name}' Rmode set to {bone.rotation_mode}")
    
    # Log world matrix BEFORE conversion
    world_matrix_before = bone.matrix.copy()
    logger.debug(f" |  # BEFORE conversion:")
    for line in str(world_matrix_before).split('\n'):
        logger.debug(f" |  |  {line}")
    logger.debug(f" |  |  Rotation mode: {bone.rotation_mode}")

    # Store current rotation matrix
    rot_matrix = bone.matrix_basis.to_3x3()
    for line in str(rot_matrix).split('\n'):
        logger.debug(f" |  |  {line}")
    logger.debug(f" |  # Stored '{bone_name}' rotation matrix as {original_rmode}")

    # Set to target rmode, and keyframe it
    bone.rotation_mode = target_rmode
    bone.keyframe_insert("rotation_mode", frame=current_frame, group=bone_name)
    logger.debug(f" |  # Rmode set to {bone.rotation_mode}")

    # Convert and apply the rotation to the new mode and keyframe rotations
    if target_rmode == 'QUATERNION':
        bone.rotation_quaternion = rot_matrix.to_quaternion()
        logger.debug(f" |  |  Converted to quaternion: {bone.rotation_quaternion}")
        bone.keyframe_insert(data_path="rotation_quaternion")
    elif target_rmode == 'AXIS_ANGLE':
        quat = rot_matrix.to_quaternion()
        axis, angle = quat.to_axis_angle()
        # bone.rotation_axis_angle expects [angle, axis_x, axis_y, axis_z]
        bone.rotation_axis_angle = [angle, axis.x, axis.y, axis.z]
        logger.debug(f" |  |  Converted to axis-angle: {bone.rotation_axis_angle}")
        bone.keyframe_insert(data_path="rotation_axis_angle")
    else:  # Euler modes (XYZ, XZY, YXZ, YZX, ZXY, ZYX)
        bone.rotation_euler = rot_matrix.to_euler(target_rmode)
        logger.debug(f" |  |  Converted to euler: {bone.rotation_euler}")
        bone.keyframe_insert(data_path="rotation_euler")
    
    # Log world matrix AFTER conversion
    world_matrix_after = bone.matrix.copy()
    logger.debug(f" |  # AFTER conversion:")
    for line in str(world_matrix_after).split('\n'):
        logger.debug(f" |  |  {line}")
    logger.debug(f" |  |  Rotation mode: {bone.rotation_mode}")
    
    # Check if matrices match (simplified calculation)
    diff_matrix = world_matrix_before - world_matrix_after
    matrix_diff = sum(val**2 for row in diff_matrix for val in row) ** 0.5
    if matrix_diff > 0.0001:
        logger.warning(f" |  |  MISMATCH! Matrix difference: {matrix_diff}")
    else:
        logger.debug(f" |  |  Matrices match (diff: {matrix_diff})")

    
    logger.debug(f" |  # Keyframed '{bone_name}' rotations")


def process_bone_conversion(
    context: Context,
    bone: PoseBone,
    list_frames: Optional[List[float]] = None,
) -> None:
    """Process the complete conversion for a single bone."""
    CRM_Properties = context.scene.CRM_Properties
    scene = context.scene
    # frame_end = scene.frame_end

    setup_bone_for_conversion(context, bone)
    dprint(f" # Target Rmode will be {CRM_Properties.targetRmode}")

    locks = prepare_bone_locks(bone)
    if list_frames is None:
        list_frames = get_list_frames(bone)

    if not list_frames:
        logger.debug(f" # No rotation keyframes found on '{bone.name}'.")
        if CRM_Properties.preserveLocks:
            toggle_rotation_locks(bone, 'ON', locks)
        return

    original_rmode = setup_initial_keyframe(bone, list_frames[0])

    # Process each frame in the frames list
    for frame in list_frames:
        scene.frame_set(int(frame))
        dprint(f" |  # Jumped to frame {frame}")

        update_progress(context)

        convert_frame_rotation(context, bone, original_rmode)

        # CLEANUP
        # jump_next_frame(context)

        # if current_frame == context.scene.frame_current:
        #     break

    # Restore locks if needed
    if CRM_Properties.preserveLocks:
        toggle_rotation_locks(bone, 'ON', locks)
        dprint(" |  # Reverted rotation locks")

    logger.debug(f" # No more keyframes on '{bone.name}'.#")


def init_progress(context: Context, total_steps: int) -> None:
    """Initialize the progress tracking."""
    global _progress_counter
    progress_max = total_steps

    # Safety checks
    if progress_max <= 0:
        dprint(
            f"Warning: Invalid progress_max ({progress_max}). Using fallback."
        )
        progress_max = 1

    _progress_counter = 0

    try:
        context.window_manager.progress_begin(0, progress_max)
    except Exception as e:
        dprint(f"Failed to initialize progress bar: {e}")


def update_progress(context: Context) -> None:
    """Update the progress counter and progress bar"""
    global _progress_counter
    _progress_counter += 1
    try:
        context.window_manager.progress_update(_progress_counter)
    except Exception as e:
        dprint(f"Failed to update progress: {e}")


def finish_progress(context: Context) -> None:
    """Finish the progress tracking."""
    try:
        context.window_manager.progress_end()
        dprint("Progress bar finished successfully")
    except Exception as e:
        dprint(f"Failed to finish progress bar: {e}")


def store_initial_state(context: Context) -> None:
    """Store the initial state before conversion."""
    scene = context.scene
    selection = list(context.selected_pose_bones)
    scene["crm_initial_frame"] = scene.frame_current

    # Store bone names instead of bone objects
    scene["crm_initial_selection"] = [bone.name for bone in selection]

    # Store the active pose bone name, not the bone object
    if context.active_pose_bone:
        scene["crm_initial_active"] = context.active_pose_bone.name
    elif selection:
        scene["crm_initial_active"] = selection[0].name
    else:
        scene["crm_initial_active"] = ""


def restore_initial_state(context: Context) -> None:
    """Restore the initial state after conversion."""
    CRM_Properties = context.scene.CRM_Properties
    scene = context.scene

    if CRM_Properties.jumpInitFrame:
        initial_frame = scene.get('crm_initial_frame', 1)
        context.scene.frame_set(int(initial_frame))

    if CRM_Properties.preserveSelection:
        # Restore selection from stored bone names
        selected_bone_names = scene.get('crm_initial_selection', [])
        initial_active_bone_name = scene.get('crm_initial_active', "")
        pose_bones = context.object.pose.bones
        data_bones = context.object.data.bones

        deselect_all_bones()

        # Select bones by name
        # Ensure we're working with strings
        if isinstance(selected_bone_names, (list, tuple)):
            for bone_name in selected_bone_names:
                bone_name_str = str(bone_name)
                dprint(f"Trying to select bone: '{bone_name_str}'")
                if bone_name_str in pose_bones:
                    set_bone_select(pose_bones[bone_name_str], True)

        # Set active bone by name
        if initial_active_bone_name:
            active_bone_name_str = str(initial_active_bone_name)
            if active_bone_name_str and active_bone_name_str in data_bones:
                data_bones.active = data_bones[active_bone_name_str]

    # Clean up stored data
    scene.pop("crm_initial_frame", None)
    scene.pop("crm_initial_active", None)
    scene.pop("crm_initial_selection", None)


def is_any_pose_bone_selected() -> bool:
    """
    Checks if any pose bone is selected in the armature data instead of looking
    in the viewport context, which is otherwise prone to issues if objects are 
    hidden in the viewport even if I do have them visible and selected in 
    another viewport

    Returns:
        Bool: Whether a bone is selected.
    """

    for obj in bpy.context.selected_objects:
        if obj.type == 'ARMATURE' and obj.mode == 'POSE':
            if obj.pose and any(get_bone_select(bone) for bone in obj.pose.bones):
                return True
    return False
