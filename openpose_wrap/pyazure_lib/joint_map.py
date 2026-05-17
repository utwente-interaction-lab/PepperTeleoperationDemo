"""
Azure Kinect Body Tracking SDK (K4ABT) joint index -> BODY_25 key mapping.

The original pipeline (OpenPose + Kinect v2) produced a dict keyed by
BODY_25 string indices:
    '0'  = Nose
    '1'  = Neck
    '2'  = RShoulder
    '3'  = RElbow
    '4'  = RWrist
    '5'  = LShoulder
    '6'  = LElbow
    '7'  = LWrist
    '8'  = MidHip

The Azure Kinect B.T. SDK defines 32 joints via k4abt_joint_id_t.
We map the closest Azure joint to each BODY_25 key we actually use.

pykinect_azure exposes joint names as string attributes of K4ABT_JOINT_*.
The integer values below match the k4abt_joint_id_t enum.
"""

# Azure K4ABT joint ID -> BODY_25 string key
# Only the 9 indices consumed by keypoints_to_angles.py are mapped.
AZURE_TO_BODY25 = {
    # K4ABT_JOINT_NOSE  = 27
    27: '0',   # Nose

    # OpenPose "Neck" is between shoulders; Azure "spine - chest" best matches it.
    # Joint IDs:
    #   2 = spine - chest
    #   3 = neck
    #   4 = left clavicle
    2:  '1',   # Neck surrogate (K4ABT_JOINT_SPINE_CHEST = 2)

    # Right arm
    12: '2',   # RShoulder  (K4ABT_JOINT_SHOULDER_RIGHT = 12)
    13: '3',   # RElbow     (K4ABT_JOINT_ELBOW_RIGHT    = 13)
    14: '4',   # RWrist     (K4ABT_JOINT_WRIST_RIGHT    = 14)

    # Left arm
    5:  '5',   # LShoulder  (K4ABT_JOINT_SHOULDER_LEFT  = 5)
    6:  '6',   # LElbow     (K4ABT_JOINT_ELBOW_LEFT     = 6)
    7:  '7',   # LWrist     (K4ABT_JOINT_WRIST_LEFT     = 7)

    # Hip centre
    # K4ABT_JOINT_PELVIS = 0  - equivalent to OpenPose MidHip (8)
    0:  '8',   # MidHip (K4ABT_JOINT_PELVIS = 0)
}

# Inverse mapping: BODY_25 key -> Azure joint ID (convenient for lookups)
BODY25_TO_AZURE = {v: k for k, v in AZURE_TO_BODY25.items()}

# Human-readable label for each BODY_25 key
BODY25_LABELS = {
    '0': 'Nose',
    '1': 'Neck',
    '2': 'RShoulder',
    '3': 'RElbow',
    '4': 'RWrist',
    '5': 'LShoulder',
    '6': 'LElbow',
    '7': 'LWrist',
    '8': 'MidHip',
}

# Azure K4ABT confidence threshold: only accept MEDIUM (2) or HIGH (3)
# K4ABT_JOINT_CONFIDENCE_NONE = 0
# K4ABT_JOINT_CONFIDENCE_LOW  = 1
# K4ABT_JOINT_CONFIDENCE_MEDIUM = 2
# K4ABT_JOINT_CONFIDENCE_HIGH   = 3
MIN_CONFIDENCE = 2
