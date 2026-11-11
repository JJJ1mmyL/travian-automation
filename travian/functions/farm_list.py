"""Start every farm list."""

from travian.modules.farm_list import start_all_farm_lists

name = "farm_list"


def run(page, params: dict) -> dict:
    result = start_all_farm_lists(page)
    result["action"] = "start"
    return result


def telegram_menu(context: dict):
    return None


def resolve_command(data: str, session: dict):
    return None


def to_telegram_message(result: dict) -> str:
    if result.get("error"):
        return f"Farm lists failed: {result['error']}"
    if result.get("started"):
        return f"Farm lists started. Raids sent: {result.get('raids_sent', 0)}"
    return f"Farm lists not started: {result.get('reason', 'unknown')}"
