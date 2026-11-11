"""One small town-hall celebration."""

from travian.modules.celebration import start_small

name = "celebration"


def run(page, params: dict) -> dict:
    result = start_small(page)
    result["action"] = "small"
    return result


def telegram_menu(context: dict):
    return None


def resolve_command(data: str, session: dict):
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Celebration failed: {result['error']}"
    if result.get("started"):
        return "Small celebration started."
    return f"Small celebration not started: {result.get('reason', 'unknown')}"
