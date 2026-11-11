"""Hero adventures and the two bonus videos."""

from travian.keyboard import button, with_home
from travian.modules.adventures import (
    hero_status,
    list_adventures,
    open_adventures,
    start_adventure,
    video_switches,
    watch_video,
)

name = "adventure"


def run(page, params: dict) -> dict:
    action = params.get("action")
    open_adventures(page)
    if action == "list":
        return {
            "action": "list",
            "hero": hero_status(page),
            "adventures": list_adventures(page),
            "videos": video_switches(page),
        }
    if action == "start":
        result = start_adventure(page, int(params.get("index") or 0))
        result["action"] = "start"
        return result
    if action == "video":
        result = watch_video(page, params.get("kind") or "duration")
        result["action"] = "video"
        return result
    if action == "auto":
        switches = {item["kind"]: item for item in video_switches(page)}
        videos = []
        for kind in ("duration", "difficulty"):
            if (switches.get(kind) or {}).get("status") != "ready":
                continue
            videos.append(watch_video(page, kind))
        return {"action": "auto", "videos": videos, "start": start_adventure(page, 0)}
    return {"error": "unknown adventure action"}


def _video_button(kind: str, status: str) -> dict:
    label = "Duration" if kind == "duration" else "Difficulty"
    if status == "watched":
        return button(f"{label} (watched)", f"a:w:{kind}")
    return button(f"{label} video", f"a:v:{kind}")


def telegram_menu(context: dict):
    result = context.get("result") or {}
    if result.get("action") != "list":
        return None
    statuses = {item["kind"]: item.get("status") or "" for item in result.get("videos") or []}
    rows = [[_video_button("duration", statuses.get("duration", "")), _video_button("difficulty", statuses.get("difficulty", ""))]]
    for index, adventure in enumerate(result.get("adventures") or []):
        place = adventure.get("place") or f"Adventure {index + 1}"
        rows.append([button(f"{index + 1}. {place}"[:40], f"a:s:{index}")])
    return with_home(rows)


def resolve_command(data: str, session: dict):
    if data.startswith("a:w:"):
        return {"type": "toast", "text": "Already watched"}
    if data.startswith("a:s:"):
        return {"type": "task", "function": name, "params": {"action": "start", "index": int(data.split(":")[2])}}
    if data.startswith("a:v:"):
        return {"type": "task", "function": name, "params": {"action": "video", "kind": data.split(":")[2]}}
    return None


QUIET_START = {"hero is not in the village", "no adventure"}


def _auto_message(result: dict) -> str:
    lines = []
    for video in result.get("videos") or []:
        if video.get("watched"):
            lines.append(f"{video.get('kind')} video watched.")
        else:
            lines.append(f"{video.get('kind')} video: {video.get('reason', 'not watched')}")
    started = result.get("start") or {}
    if started.get("started"):
        adventure = started.get("adventure") or {}
        place = adventure.get("place") or "adventure"
        lines.append(f"Adventure started: {place}")
    elif started.get("reason") not in QUIET_START:
        lines.append(f"Adventure not started: {started.get('reason', 'unknown')}")
    return "\n".join(lines)


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Adventure failed: {result['error']}"
    action = result.get("action")
    if action == "auto":
        return _auto_message(result)
    if action == "list":
        videos = result.get("videos") or []
        video_text = ", ".join(f"{item['kind']} {item['status']}" for item in videos) or "none"
        return (
            f"{result.get('hero') or 'Hero status unknown'}\n"
            f"Adventures: {len(result.get('adventures') or [])}\n"
            f"Videos: {video_text}"
        )
    if action == "video":
        if result.get("watched"):
            return f"{result.get('kind')} video watched."
        return f"{result.get('kind')} video: {result.get('reason', 'not watched')}"
    if not result.get("started"):
        return f"Adventure not started: {result.get('reason', 'unknown')}"
    adventure = result.get("adventure") or {}
    place = adventure.get("place") or "adventure"
    return f"Adventure started: {place}\n{result.get('hero', '')}".strip()
