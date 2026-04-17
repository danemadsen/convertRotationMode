# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Set
import bpy
from bpy.types import Operator
from bpy.types import Context
from .utils import (
    activate_armature_action_assignment,
    collect_armature_action_assignments,
    dprint,
    get_selected_action_assignments,
    get_list_frames_from_action,
    process_bone_conversion,
    restore_armature_animation_state,
    store_initial_state,
    store_armature_animation_state,
    restore_initial_state,
    init_progress,
    finish_progress,
    is_any_pose_bone_selected,
)
from .bl_logger import logger


class CRM_OT_convert_rotation_mode(Operator):
    """Convert the selected pose bones across the checked armature actions."""
    bl_idname = "crm.convert_rotation_mode"
    bl_label = "Convert Rotation Mode"
    bl_description = (
        "Convert the selected bones' rotation mode on the checked actions "
        "from the action list."
    )
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context: Context) -> bool:
        """Filter for pose mode, selected bones"""
        is_pose_mode = context.mode == 'POSE'
        has_selected_bones = is_any_pose_bone_selected()

        return is_pose_mode and has_selected_bones

    def execute(self, context: Context) -> Set[str]:
        """Convert selected bones on the checked actions for the armature."""

        armature = context.object
        target_rmode = context.scene.CRM_Properties.targetRmode
        selected_bone_names = [
            bone.name for bone in context.selected_pose_bones
        ]
        bone_count = len(selected_bone_names)
        action_assignments = collect_armature_action_assignments(armature)

        dprint(
            f"Starting conversion for {bone_count} bones: "
            f"{selected_bone_names}"
        )

        if not action_assignments:
            self.report({"WARNING"}, "No actions are available to convert.")
            return {'CANCELLED'}

        selected_action_assignments = get_selected_action_assignments(
            context.scene,
            armature,
            action_assignments,
        )

        if not selected_action_assignments:
            self.report(
                {"WARNING"},
                "Select at least one action to convert in the addon panel.",
            )
            return {'CANCELLED'}

        assignments_with_frames = []
        for assignment in selected_action_assignments:
            list_frames = get_list_frames_from_action(
                assignment.action,
                assignment.slot,
            )
            if not list_frames:
                dprint(
                    f"Skipping {assignment.label}: "
                    f"'{assignment.action.name}' has no rotation keyframes."
                )
                continue

            assignments_with_frames.append((assignment, list_frames))

        if not assignments_with_frames:
            self.report(
                {"WARNING"},
                "The selected actions do not contain rotation keyframes to convert.",
            )
            return {'CANCELLED'}

        store_initial_state(context)
        animation_state = store_armature_animation_state(armature)
        init_progress(
            context,
            bone_count * sum(
                len(list_frames) for _, list_frames in assignments_with_frames
            ),
        )

        try:
            for assignment, list_frames in assignments_with_frames:
                logger.info(
                    " ## Working on %s: '%s'",
                    assignment.label,
                    assignment.action.name,
                )
                activate_armature_action_assignment(armature, assignment)

                for bone_name in selected_bone_names:
                    if bone_name in armature.pose.bones:
                        current_bone = armature.pose.bones[bone_name]
                        process_bone_conversion(
                            context,
                            current_bone,
                            list_frames,
                        )
                    else:
                        dprint(f"Warning: Bone '{bone_name}' not found.")

            logger.info(" # No more bones to work on.")
        finally:
            finish_progress(context)
            restore_armature_animation_state(armature, animation_state)
            restore_initial_state(context)

        action_count = len(assignments_with_frames)
        self.report(
            {"INFO"},
            f"Converted {bone_count} bone(s) across {action_count} "
            f"action(s) to '{target_rmode}'"
        )

        return {'FINISHED'}
