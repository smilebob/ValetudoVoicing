"""Supported Roborock robot profiles and Valetudo model auto-detection."""

from dataclasses import dataclass
import httpx


@dataclass(frozen=True)
class RobotProfile:
    """Capabilities and voicepack format for a Roborock model under Valetudo."""

    id: str
    name: str
    features: tuple[str, ...]
    audio_format: str = "wav"
    encrypt: bool = True
    valetudo_hints: tuple[str, ...] = ()


ROBOROCK_PROFILES: list[RobotProfile] = [
    RobotProfile(
        id="roborock_v1",
        name="Xiaomi Mi Robot Vacuum (V1)",
        features=("base",),
        valetudo_hints=("rockrobo.vacuum.v1", "mi robot", "v1"),
    ),
    RobotProfile(
        id="roborock_s4",
        name="Roborock S4",
        features=("base",),
        valetudo_hints=("roborock.vacuum.s4", "s4"),
    ),
    RobotProfile(
        id="roborock_s4max",
        name="Roborock S4 Max",
        features=("base",),
        valetudo_hints=("roborock.vacuum.a19", "s4 max", "s4max"),
    ),
    RobotProfile(
        id="roborock_s5",
        name="Roborock S5",
        features=("base",),
        valetudo_hints=("roborock.vacuum.s5", "s50", "s55", "s5"),
    ),
    RobotProfile(
        id="roborock_s5max",
        name="Roborock S5 Max",
        features=("base", "mop"),
        valetudo_hints=("roborock.vacuum.s5e", "s5 max", "s5max"),
    ),
    RobotProfile(
        id="roborock_s6",
        name="Roborock S6 / S6 Pure",
        features=("base", "mop"),
        valetudo_hints=("roborock.vacuum.s6", "roborock.vacuum.a08", "s6 pure", "s6"),
    ),
    RobotProfile(
        id="roborock_s6maxv",
        name="Roborock S6 MaxV",
        features=("base", "mop"),
        valetudo_hints=("roborock.vacuum.a10", "s6 maxv", "s6maxv"),
    ),
    RobotProfile(
        id="roborock_s7",
        name="Roborock S7 / S7+",
        features=("base", "mop", "autodock"),
        valetudo_hints=("roborock.vacuum.a15", "s7+", "s7"),
    ),
    RobotProfile(
        id="roborock_s7pro",
        name="Roborock S7 MaxV / S7 Pro Ultra",
        features=("base", "mop", "autodock"),
        valetudo_hints=("roborock.vacuum.a27", "roborock.vacuum.a62", "s7 maxv", "s7 pro"),
    ),
    RobotProfile(
        id="roborock_q7max",
        name="Roborock Q7 Max / Q7 Max+",
        features=("base", "mop", "autodock"),
        valetudo_hints=("roborock.vacuum.a38", "q7 max", "q7max"),
    ),
]

ROBOT_PROFILE_MAP: dict[str, RobotProfile] = {r.id: r for r in ROBOROCK_PROFILES}


def get_robot_profile(robot_id: str) -> RobotProfile:
    """Return a RobotProfile by ID (case-insensitive)."""
    norm = robot_id.strip().lower()
    if norm not in ROBOT_PROFILE_MAP:
        raise ValueError(
            f"Unknown robot '{robot_id}'. Available: {', '.join(ROBOT_PROFILE_MAP.keys())}"
        )
    return ROBOT_PROFILE_MAP[norm]


def match_robot_model(model_text: str) -> RobotProfile | None:
    """Match a Valetudo modelName / modelDetails string to a RobotProfile."""
    lower = model_text.strip().lower()
    if not lower:
        return None
    # Check longest hints first so "s5 max" matches before "s5"
    ranked: list[tuple[int, RobotProfile]] = []
    for profile in ROBOROCK_PROFILES:
        for hint in profile.valetudo_hints:
            if hint in lower:
                ranked.append((len(hint), profile))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def detect_robot_from_valetudo(robot_ip: str, timeout: float = 5.0) -> tuple[RobotProfile | None, str]:
    """Query Valetudo `GET /api/v2/robot` and return (matched_profile, raw_model_name)."""
    url = f"http://{robot_ip}/api/v2/robot"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    model_name = str(data.get("modelName", "") or data.get("modelDetails", {}).get("modelName", ""))
    manufacturer = str(data.get("manufacturer", ""))
    combined = f"{manufacturer} {model_name}".strip()
    return match_robot_model(combined), combined
