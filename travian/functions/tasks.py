"""Collect ready progressive-task rewards."""

from travian.modules.tasks import collect_rewards

name = "tasks"


def run(page, params: dict) -> dict:
    if params.get("action") != "collect":
        return {"error": "unknown tasks action"}
    return collect_rewards(page)


def telegram_menu(context: dict):
    return None


def resolve_command(data: str, session: dict):
    return None


def _line(item: dict) -> str:
    parts = []
    if item.get("resources"):
        parts.append(f"{item['resources']} resources")
    if item.get("xp"):
        parts.append(f"{item['xp']} XP")
    detail = f": {', '.join(parts)}" if parts else ""
    return f"Collected {item.get('title') or 'Task'}{detail}"


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Tasks failed: {result['error']}"
    lines = [_line(item) for item in result.get("collected") or []]
    for item in result.get("failed") or []:
        lines.append(f"{item.get('title') or 'Task'}: {item.get('reason') or 'not collected'}")
    return "\n".join(lines)
