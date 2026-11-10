"""Start every farm list on a timer, and answer Telegram commands.

Commands, from the chat in TELEGRAM_CHAT_ID:

/village     current village stock and production
/adventures  outstanding adventures and video status
/watch       watch every bonus video that is ready
/startadv    send the hero on the first adventure
/buildings   village building slots
/build       construct a building; optional video and inventory
/upgrade     upgrade a building; optional video and inventory
/fields      resource fields
/upfield     upgrade a resource field; optional video and inventory
"""

import functools
import os
import queue
import random
import threading
import time

print = functools.partial(print, flush=True)

from telegram_bot import load_store, save_store
from travian.browser import browser_page
from travian.config import FARM_LIST_DELAY_MAX, FARM_LIST_DELAY_MIN
from travian.modules.adventures import (
    hero_status,
    list_adventures,
    open_adventures,
    start_adventure,
    video_switches,
    watch_video,
)
from travian.modules.farm_list import start_all_farm_lists
from travian.modules.buildings import build, list_buildings, upgrade
from travian.modules.login import login
from travian.modules.resources import list_fields, read_resource_page, upgrade_field
from travian.modules.telegram import get_updates, send_message

HELP = "\n".join(
    [
        "/village — village stock and production",
        "/adventures — outstanding adventures and video status",
        "/watch — watch ready bonus videos",
        "/watch duration — watch the duration video",
        "/watch difficulty — watch the difficulty video",
        "/startadv — start the first adventure",
        "/startadv 2 — start adventure 2",
        "/buildings — village building slots",
        "/build 21 cranny — construct a building",
        "/build 21 cranny video — construct 25% faster",
        "/build 21 cranny inventory — construct with hero inventory",
        "/upgrade 19 — upgrade a building",
        "/upgrade 19 video — upgrade 25% faster",
        "/upgrade 19 inventory — upgrade with hero inventory",
        "/fields — resource fields",
        "/upfield 3 — upgrade a resource field",
        "/upfield 3 video — upgrade a field 25% faster",
        "/upfield 3 inventory — upgrade a field with hero inventory",
    ]
)


def allowed(chat_id) -> bool:
    expected = os.environ.get("TELEGRAM_CHAT_ID", "")
    return bool(expected) and str(chat_id) == str(expected)


def command_parts(text: str) -> tuple[str, str]:
    parts = (text or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    name = parts[0].split("@", 1)[0].lstrip("/").lower()
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    return name, arg


def format_village(data: dict) -> str:
    stock = data["stock"]
    production = data["production_per_hour"]
    lines = [
        f"{data['village']} {data['coordinates']}",
        f"Population {data['population']}  Loyalty {data['loyalty']}",
        f"Wood {stock['lumber']}/{data['warehouse_capacity']} ({production.get('lumber', 0)}/h)",
        f"Clay {stock['clay']}/{data['warehouse_capacity']} ({production.get('clay', 0)}/h)",
        f"Iron {stock['iron']}/{data['warehouse_capacity']} ({production.get('iron', 0)}/h)",
        f"Crop {stock['crop']}/{data['granary_capacity']} ({production.get('crop', 0)}/h)",
        f"Free crop {stock['free_crop']}",
    ]
    if data["building_queue"]:
        lines.append("Queue: " + " | ".join(data["building_queue"]))
    return "\n".join(lines)


def format_adventures(hero: str, adventures: list, switches: list) -> str:
    lines = [
        hero or "Hero status unknown",
        f"Outstanding adventures: {len(adventures)}",
    ]
    for number, adventure in enumerate(adventures, start=1):
        lines.append(
            f"{number}. {adventure['place']} {adventure['distance']} "
            f"{adventure['duration']} {adventure['danger']}".strip()
        )
    if switches:
        lines.append("Videos:")
        for switch in switches:
            lines.append(f"- {switch['kind']}: {switch['status']}")
    else:
        lines.append("Videos: none")
    return "\n".join(lines)


def format_watch(results: list) -> str:
    lines = []
    for result in results:
        if result.get("watched"):
            lines.append(f"{result['kind']}: watched")
        else:
            lines.append(f"{result['kind']}: {result.get('reason', 'not watched')}")
    return "\n".join(lines) or "No video is ready"


def format_farms(result: dict) -> str:
    if result.get("started"):
        return f"Farm lists started. Raids sent: {result.get('raids_sent', 0)}"
    return f"Farm lists not started: {result.get('reason', 'unknown')}"


def show_village(page) -> str:
    return format_village(read_resource_page(page))


def show_adventures(page) -> str:
    open_adventures(page)
    return format_adventures(hero_status(page), list_adventures(page), video_switches(page))


def watch(page, arg: str) -> str:
    open_adventures(page)
    if arg:
        if arg not in ("duration", "difficulty"):
            return "Use /watch, /watch duration, or /watch difficulty"
        return format_watch([watch_video(page, arg)])
    ready = [item["kind"] for item in video_switches(page) if item["ready"]]
    if not ready:
        return "No video is ready"
    return format_watch([watch_video(page, kind) for kind in ready])


def slot_action(arg: str) -> tuple[int | None, bool, bool, str]:
    parts = arg.split()
    if not parts or not parts[0].isdigit():
        return None, False, False, arg
    watch = False
    inventory = False
    while len(parts) > 1 and parts[-1] in ("video", "inventory"):
        if parts[-1] == "video":
            watch = True
        else:
            inventory = True
        parts.pop()
    return int(parts[0]), watch, inventory, " ".join(parts[1:])


def format_buildings(buildings: list) -> str:
    lines = []
    for item in buildings:
        if item["empty"]:
            line = f"{item['slot']} empty"
        else:
            line = f"{item['slot']} {item['name']} {item['level']}"
        if item["available"]:
            line += " ready"
        lines.append(line)
    return "\n".join(lines) or "No building slots"


def format_fields(fields: list) -> str:
    lines = []
    for field in fields:
        line = f"{field['slot']} {field['name']} {field['level']}"
        if field["under_construction"]:
            line += " building"
        elif field["available"]:
            line += " ready"
        lines.append(line)
    return "\n".join(lines) or "No resource fields"


def format_construction(result: dict, action: str) -> str:
    if not result.get("started"):
        return f"{action} not started: {result.get('reason') or 'unknown'}"
    label = result.get("name") or f"slot {result.get('slot')}"
    notes = []
    if result.get("use_inventory"):
        notes.append("inventory")
    if result.get("watch_video"):
        notes.append("25% faster")
    if notes:
        label += " (" + ", ".join(notes) + ")"
    return f"{action} started: {label}"


def show_buildings(page) -> str:
    return format_buildings(list_buildings(page))


def show_fields(page) -> str:
    return format_fields(list_fields(page))


def construct(page, arg: str) -> str:
    slot, watch, inventory, building = slot_action(arg)
    if slot is None or not building:
        return "Use /build 21 cranny, /build 21 cranny video, or /build 21 cranny inventory"
    return format_construction(
        build(page, slot, building, watch_video=watch, use_inventory=inventory),
        "Build",
    )


def upgrade_building(page, arg: str) -> str:
    slot, watch, inventory, extra = slot_action(arg)
    if slot is None or extra:
        return "Use /upgrade 19, /upgrade 19 video, or /upgrade 19 inventory"
    return format_construction(upgrade(page, slot, watch_video=watch, use_inventory=inventory), "Upgrade")


def upgrade_resource(page, arg: str) -> str:
    slot, watch, inventory, extra = slot_action(arg)
    if slot is None or extra:
        return "Use /upfield 3, /upfield 3 video, or /upfield 3 inventory"
    return format_construction(
        upgrade_field(page, slot, watch_video=watch, use_inventory=inventory),
        "Field upgrade",
    )


def start(page, arg: str) -> str:
    number = 1
    if arg:
        if not arg.isdigit() or int(arg) < 1:
            return "Use /startadv or /startadv 2"
        number = int(arg)
    open_adventures(page)
    result = start_adventure(page, number - 1)
    if not result.get("started"):
        return f"Adventure not started: {result.get('reason', 'unknown')}"
    adventure = result.get("adventure") or {}
    place = adventure.get("place") or f"#{number}"
    return f"Adventure started: {place}\n{result.get('hero', '')}".strip()


def handle(page, text: str) -> str:
    name, arg = command_parts(text)
    if name in ("help", "commands"):
        return HELP
    if name in ("village", "status"):
        return show_village(page)
    if name in ("adventures", "adventure"):
        return show_adventures(page)
    if name == "watch":
        return watch(page, arg)
    if name == "startadv":
        return start(page, arg)
    if name == "buildings":
        if arg:
            return "Use /buildings"
        return show_buildings(page)
    if name == "build":
        return construct(page, arg)
    if name == "upgrade":
        return upgrade_building(page, arg)
    if name == "fields":
        if arg:
            return "Use /fields"
        return show_fields(page)
    if name == "upfield":
        return upgrade_resource(page, arg)
    if text.strip().startswith("/"):
        return HELP
    return ""


_farm_lock = threading.Lock()
_farm_queued = False


def page_closed(page, error: Exception) -> bool:
    message = str(error).lower()
    if "has been closed" in message or "target closed" in message:
        return True
    try:
        return page.is_closed()
    except Exception:
        return True


def notify(text: str, chat_id: str | None = None) -> None:
    if not text:
        return
    try:
        send_message(text, chat_id=chat_id)
    except Exception as error:
        print(f"telegram notify failed: {error}")


def on_login_page(page) -> bool:
    try:
        return page.get_by_role("textbox", name="Enter your email address or").is_visible()
    except Exception:
        return False


def with_login_retry(page, action):
    try:
        return action()
    except Exception as error:
        if page_closed(page, error) or not on_login_page(page):
            raise
        print("redirected to login, logging in again")
        login(page)
        return action()


def run_farms(page) -> None:
    try:
        message = format_farms(with_login_retry(page, lambda: start_all_farm_lists(page)))
    except Exception as error:
        if page_closed(page, error):
            raise
        message = f"Farm lists failed: {error}"
    print(message)
    notify(message)


def run_command(page, task: dict) -> None:
    try:
        reply = with_login_retry(page, lambda: handle(page, task["text"]))
    except Exception as error:
        if page_closed(page, error):
            raise
        reply = f"Failed: {error}"
        print(reply)
    notify(reply, chat_id=task["chat_id"])


def enqueue_farms(tasks: queue.Queue) -> None:
    global _farm_queued
    with _farm_lock:
        if _farm_queued:
            print("farm lists already queued")
            return
        _farm_queued = True
        tasks.put({"kind": "farms"})


def take_farm() -> None:
    global _farm_queued
    with _farm_lock:
        _farm_queued = False


def enqueue_update(tasks: queue.Queue, update: dict, state: dict) -> None:
    state["update_id"] = str(update["update_id"])
    save_store(state)
    message = update.get("message") or update.get("edited_message")
    if not message or not allowed((message.get("chat") or {}).get("id")):
        return
    text = message.get("text") or ""
    if not text:
        return
    print(f"command {text}")
    tasks.put({"kind": "command", "text": text, "chat_id": str(message["chat"]["id"])})


def poll_timeout(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining < 1:
        return 0
    return min(30, int(remaining))


def work(tasks: queue.Queue, stopped: threading.Event) -> None:
    try:
        with browser_page() as page:
            login(page)
            print("logged in")
            while not stopped.is_set():
                try:
                    task = tasks.get(timeout=1)
                except queue.Empty:
                    continue
                if task["kind"] == "farms":
                    take_farm()
                    run_farms(page)
                else:
                    run_command(page, task)
    except Exception as error:
        print(f"browser stopped: {error}")
    finally:
        stopped.set()


def produce(tasks: queue.Queue, stopped: threading.Event) -> None:
    state = load_store()
    offset = int(state["update_id"]) + 1 if state.get("update_id") else None
    next_farm = time.monotonic()
    while not stopped.is_set():
        if time.monotonic() >= next_farm:
            enqueue_farms(tasks)
            delay = random.randint(FARM_LIST_DELAY_MIN, FARM_LIST_DELAY_MAX)
            next_farm = time.monotonic() + delay
            print(f"next farm lists in {delay}s")
        try:
            updates = get_updates(offset, poll_timeout(next_farm))
        except Exception as error:
            print(f"poll failed: {error}")
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            enqueue_update(tasks, update, state)


def main() -> None:
    tasks = queue.Queue()
    stopped = threading.Event()
    # Playwright's sync API has to stay on the main thread. A background
    # thread can launch Camoufox and then fail new_page with a closed browser.
    poller = threading.Thread(target=produce, args=(tasks, stopped), name="telegram", daemon=True)
    poller.start()
    try:
        work(tasks, stopped)
    finally:
        stopped.set()
        poller.join(timeout=40)


if __name__ == "__main__":
    main()
