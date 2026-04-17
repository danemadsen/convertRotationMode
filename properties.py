# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


class CRM_ActionSelectionItem(PropertyGroup):
    identifier: StringProperty(
        name="Identifier",
        description="Internal identifier for an action/slot pair.",
    )

    action_name: StringProperty(
        name="Action Name",
        description="The Blender action datablock name.",
    )

    slot_identifier: StringProperty(
        name="Slot Identifier",
        description="The Blender action slot identifier.",
    )

    display_name: StringProperty(
        name="Display Name",
        description="Friendly name shown in the UI.",
    )

    source_label: StringProperty(
        name="Source Label",
        description="Where this action assignment was discovered.",
    )

    selected: BoolProperty(
        name="Convert",
        description="Convert this action when running the operator.",
        default=True,
    )


class CRM_Props(PropertyGroup):
    targetRmode: EnumProperty(
        name='Target Rotation Mode',
        description='Target Rotation Mode for the conversion.',
        items=[
            ("XYZ", "XYZ Euler", "XYZ Euler - Rotation Order - prone to Gimbal Lock (default)."),
            ("XZY", "XZY Euler", "XZY Euler - Rotation Order - prone to Gimbal Lock."),
            ("YXZ", "YXZ Euler", "YXZ Euler - Rotation Order - prone to Gimbal Lock."),
            ("YZX", "YZX Euler", "YZX Euler - Rotation Order - prone to Gimbal Lock."),
            ("ZXY", "ZXY Euler", "ZXY Euler - Rotation Order - prone to Gimbal Lock."),
            ("ZYX", "ZYX Euler", "ZYX Euler - Rotation Order - prone to Gimbal Lock."),
            ("AXIS_ANGLE", "Axis Angle (WXYZ)", "Axis Angle (WXYZ) – Defines a rotation around some axis defined by 3D-Vector."),
            ("QUATERNION", "Quaternion (WXYZ)", "Quaternion (WXYZ) – No Gimbal Lock but awful for animators in Graph Editor."),
        ],
        default='XYZ'
    )

    jumpInitFrame: BoolProperty(
        name="Preserve current frame",
        description='Preserve the current frame after conversion is done.',
        default=True
    )

    preserveLocks: BoolProperty(
        name="Preserve Locks",
        description="Preserves lock states on rotation channels.",
        default=True
    )

    preserveSelection: BoolProperty(
        name="Preserve Selection",
        description="Preserves selection.",
        default=True
    )

    actionSelectionOwner: StringProperty(
        name="Action Selection Owner",
        description="Internal armature name used to keep action lists in sync.",
        default="",
        options={'HIDDEN'},
    )

    actionSelections: CollectionProperty(type=CRM_ActionSelectionItem)
