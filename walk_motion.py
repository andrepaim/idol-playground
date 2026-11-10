"""Bounded canine profile and periodic, four-beat walking trajectories (CPU only)."""

import json
import math
import struct

PROFILE = "canine-34-v1"
PARENTS = [
    None,
    0,
    1,
    2,
    3,
    4,
    4,
    6,
    7,
    8,
    2,
    10,
    11,
    12,
    13,
    2,
    15,
    16,
    17,
    18,
    0,
    20,
    0,
    22,
    23,
    24,
    25,
    26,
    0,
    28,
    29,
    30,
    31,
    32,
]
PAWS = {"fore_left": "bone_14", "fore_right": "bone_19", "hind_left": "bone_27", "hind_right": "bone_33"}
DUTY = 0.65
CENTERS = {
    role: (landing + DUTY / 2) % 1
    for role, landing in [("hind_left", 0), ("fore_left", 0.25), ("hind_right", 0.5), ("fore_right", 0.75)]
}


def foot_path(phase, center, stride, lift):
    if not all(math.isfinite(x) for x in (phase, center, stride, lift)) or stride <= 0 or lift <= 0:
        raise ValueError("Invalid foot trajectory")
    u = (phase - center + 0.5) % 1 - 0.5
    if abs(u) <= DUTY / 2:
        return -stride * u, 0, True
    if u < 0:
        u += 1
    q = (u - DUTY / 2) / (1 - DUTY)
    h00 = 2 * q**3 - 3 * q * q + 1
    h10 = q**3 - 2 * q * q + q
    h01 = -2 * q**3 + 3 * q * q
    h11 = q**3 - q * q
    x = h00 * (-stride * DUTY / 2) + h01 * (stride * DUTY / 2) + (h10 + h11) * (-stride * (1 - DUTY))
    return x, lift * math.sin(math.pi * q) ** 2, False


def validate_roles(roles, reviewed):
    if not reviewed:
        raise ValueError("Review the four paw assignments before creating a walk.")
    if not isinstance(roles, dict) or set(roles) != set(PAWS) or len(set(roles.values())) != 4:
        raise ValueError("Assign four distinct paws.")
    for prefix in ("fore", "hind"):
        if {roles[prefix + "_left"], roles[prefix + "_right"]} != {PAWS[prefix + "_left"], PAWS[prefix + "_right"]}:
            raise ValueError("This profile supports left/right swaps within matching fore or hind chains only.")
    return dict(roles)


def profile_from_glb(data):
    unsupported = {"supported": False, "reason": "Walking currently requires the reviewed 34-bone canine topology."}
    try:
        if data[:4] != b"glTF" or len(data) < 20:
            return unsupported
        length = struct.unpack_from("<I", data, 12)[0]
        doc = json.loads(data[20 : 20 + length])
        nodes = doc["nodes"]
        skins = doc["skins"]
        if len(skins) != 1 or len(skins[0]["joints"]) != 34:
            return unsupported
        joints = skins[0]["joints"]
        names = {nodes[i]["name"]: i for i in joints}
        if set(names) != {f"bone_{i}" for i in range(34)}:
            return unsupported
        parents = {}
        for i, node in enumerate(nodes):
            for child in node.get("children", []):
                if child in parents:
                    raise ValueError("Multiple parents")
                parents[child] = i
        for i, parent in enumerate(PARENTS):
            actual = parents.get(names[f"bone_{i}"])
            if parent is None:
                if actual in joints:
                    return unsupported
            elif actual != names[f"bone_{parent}"]:
                return unsupported
        return {
            "supported": True,
            "profile": PROFILE,
            "paws": dict(PAWS),
            "reason": "Experimental canine profile. Inspect paw assignments and the resulting deformation.",
        }
    except (ValueError, KeyError, TypeError, IndexError, struct.error):
        return unsupported
