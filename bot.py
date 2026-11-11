"""Three loops: Telegram menus, a scheduler, and one Camoufox consumer."""

import functools
import queue
import threading
import time

print = functools.partial(print, flush=True)

from travian.automations import AUTOMATIONS
from travian.browser import browser_page
from travian.functions import FUNCTIONS
from travian.inflight import Inflight
from travian.keyboard import with_home
from travian.menu import home_menu, on_callback
from travian.modules.login import login
from travian.modules.telegram import answer_callback, delete_message, edit_message, get_updates, send_message
from travian.notifications import NOTIFICATIONS
from travian.schedule import enqueue_due
from travian.config import JOIN_PASSCODE
from travian.store import allow_chat, flags, load, update


def page_closed(page, error: Exception) -> bool:
    message = str(error).lower()
    if "has been closed" in message or "target closed" in message:
        return True
    try:
        return page.is_closed()
    except Exception:
        return True


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


def remember_offset(update_id: int) -> None:
    def mutate(config):
        config["update_id"] = update_id

    update(mutate)


def save_cursor(cursor: dict) -> None:
    def mutate(config):
        config["automations"]["build"]["cursor"] = {
            "line": int(cursor.get("line") or 0),
            "progress": int(cursor.get("progress") or 0),
        }

    update(mutate)


def remember_condition(chat_id: str, name: str, value) -> None:
    def mutate(config):
        config["conditions"].setdefault(str(chat_id), {})[name] = value

    update(mutate)


MENU_TITLES = {
    "adventure": "Adventure",
    "buildings": "Buildings",
    "training": "Training",
    "list_fields": "Upgrade a field",
    "list_buildings": "Upgrade a building, or pick an empty slot",
    "prepare": "Build",
}


def show(chat_id, text: str, buttons, message_id: int | None = None) -> int | None:
    if not text:
        return message_id
    if message_id is not None:
        try:
            edited = edit_message(chat_id, message_id, text, buttons)
            return edited["message_id"]
        except Exception as error:
            if "not modified" in str(error).lower():
                return message_id
            print(f"edit failed: {error}")
    try:
        sent = send_message(text, chat_id=chat_id, buttons=buttons)
        return sent["message_id"]
    except Exception as error:
        print(f"telegram send failed: {error}")
        return None


def remember_menu(session: dict, message_id: int | None) -> None:
    if message_id is not None:
        session["menu_message_id"] = message_id


def edit_menu(session: dict, chat_id, text: str, buttons) -> None:
    message_id = show(chat_id, text, buttons, session.get("menu_message_id"))
    remember_menu(session, message_id)


def replace_menu(session: dict, chat_id, text: str, buttons) -> None:
    old = session.pop("menu_message_id", None)
    if old is not None:
        try:
            delete_message(chat_id, old)
        except Exception as error:
            print(f"delete menu failed: {error}")
    message_id = show(chat_id, text, buttons)
    remember_menu(session, message_id)


def user_task(chat_id, function: str, params: dict) -> dict:
    return {
        "function": function,
        "params": params,
        "requester": {"kind": "user", "chat_id": str(chat_id)},
    }


def deliver_user(sessions: dict, task: dict, result: dict) -> None:
    chat_id = str(task["requester"]["chat_id"])
    feature = FUNCTIONS[task["function"]]
    session = sessions.setdefault(chat_id, {})
    if task["function"] == "buildings" and result.get("action") in {"list_fields", "list_buildings"}:
        stored = session.setdefault("buildings", {})
        if result.get("action") == "list_fields":
            stored["fields"] = result.get("fields") or []
        else:
            stored["buildings"] = result.get("buildings") or []
    text = feature.to_telegram_message(result) or "Done."
    show(chat_id, text, None)
    buttons = feature.telegram_menu({"result": result})
    if buttons:
        title = MENU_TITLES.get(result.get("action")) or MENU_TITLES.get(task["function"], "Choose")
        replace_menu(session, chat_id, title, buttons)
        return
    menu = home_menu()
    replace_menu(session, chat_id, menu["text"], menu["buttons"])


def deliver_automation(task: dict, result: dict) -> None:
    name = task["requester"]["name"]
    if name == "build" and result.get("cursor"):
        save_cursor(result["cursor"])
    text = AUTOMATIONS[name].to_telegram_message(result)
    if not text:
        return
    config = load()
    for chat_id in config["allow_chat_ids"]:
        if flags(config, chat_id).get(name):
            show(str(chat_id), text, None)


def deliver_notification(task: dict, result: dict) -> None:
    name = task["requester"]["name"]
    chat_id = str(task["requester"]["chat_id"])
    previous = load()["conditions"].get(chat_id, {}).get(name)
    result["previous"] = previous
    text = NOTIFICATIONS[name].to_telegram_message(result)
    if "remember" in result:
        remember_condition(chat_id, name, result["remember"])
    if text:
        show(chat_id, text, None)


def handle_result(sessions: dict, item: dict) -> None:
    task = item["task"]
    result = item["result"]
    requester = task.get("requester") or {}
    kind = requester.get("kind")
    print(f"finished {task.get('function')} for {kind or 'unknown'}")
    if kind == "user":
        deliver_user(sessions, task, result)
    elif kind == "automation":
        deliver_automation(task, result)
    elif kind == "notification":
        deliver_notification(task, result)


def enqueue_outcome(tasks, session: dict, chat_id, outcome: dict, message_id: int | None) -> None:
    remember_menu(session, message_id)
    kind = outcome.get("type")
    if kind == "toast":
        return
    if kind == "menu":
        edit_menu(session, chat_id, outcome.get("text") or "Sleep bot", outcome.get("buttons"))
        return
    if kind == "task":
        tasks.put(user_task(chat_id, outcome["function"], outcome["params"]))
        edit_menu(session, chat_id, "Working...", [])
        return
    if kind == "tasks":
        for spec in outcome["tasks"]:
            tasks.put(user_task(chat_id, spec["function"], spec["params"]))
        edit_menu(session, chat_id, outcome.get("text") or "Queued.", with_home([]))


def handle_update(tasks, sessions: dict, update: dict) -> None:
    query = update.get("callback_query")
    if query:
        message = query.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id") or "")
        data = query.get("data") or ""
        if not chat_id or not _allowed(chat_id):
            try:
                answer_callback(query["id"], "Not allowed")
            except Exception as error:
                print(f"callback answer failed: {error}")
            return
        session = sessions.setdefault(chat_id, {})
        outcome = on_callback(data, session, chat_id)
        toast = outcome.get("text") if outcome.get("type") == "toast" else ""
        try:
            answer_callback(query["id"], toast)
        except Exception as error:
            print(f"callback answer failed: {error}")
        enqueue_outcome(tasks, session, chat_id, outcome, message.get("message_id"))
        return
    message = update.get("message")
    if not message or message.get("text") is None:
        return
    chat_id = str((message.get("chat") or {}).get("id") or "")
    if not _allowed(chat_id):
        text = (message.get("text") or "").strip()
        if not JOIN_PASSCODE or text != JOIN_PASSCODE:
            return
        allow_chat(chat_id)
    session = sessions.setdefault(chat_id, {})
    menu = home_menu()
    remember_menu(session, show(chat_id, menu["text"], menu["buttons"]))


def _allowed(chat_id: str) -> bool:
    from travian.store import allowed

    return allowed(chat_id)


def drain(results, sessions: dict, inflight: Inflight) -> None:
    while True:
        try:
            item = results.get_nowait()
        except queue.Empty:
            return
        try:
            handle_result(sessions, item)
        except Exception as error:
            print(f"result failed: {error}")
        finally:
            key = (item.get("task") or {}).get("inflight")
            if key:
                inflight.release(key)


def telegram_loop(tasks, results, inflight: Inflight, stopped: threading.Event) -> None:
    sessions: dict = {}
    config = load()
    offset = int(config["update_id"]) + 1 if config.get("update_id") is not None else None
    while not stopped.is_set():
        drain(results, sessions, inflight)
        try:
            updates = get_updates(offset, 1)
        except Exception as error:
            print(f"poll failed: {error}")
            stopped.wait(2)
            continue
        for update in updates:
            update_id = update["update_id"]
            offset = update_id + 1
            remember_offset(update_id)
            try:
                handle_update(tasks, sessions, update)
            except Exception as error:
                print(f"update failed: {error}")
        drain(results, sessions, inflight)


def browser_loop(tasks, results, stopped: threading.Event) -> None:
    while not stopped.is_set():
        try:
            with browser_page() as page:
                login(page)
                print("logged in")
                consume(page, tasks, results, stopped)
        except Exception as error:
            print(f"browser stopped: {error}")
            if stopped.is_set():
                return
            stopped.wait(5)


def consume(page, tasks, results, stopped: threading.Event) -> None:
    while not stopped.is_set():
        try:
            task = tasks.get(timeout=1)
        except queue.Empty:
            continue
        try:
            feature = FUNCTIONS[task["function"]]
            result = with_login_retry(page, lambda: feature.run(page, task.get("params") or {}))
        except Exception as error:
            if page_closed(page, error):
                tasks.put(task)
                raise
            result = {"error": str(error)}
        results.put({"task": task, "result": result})


def scheduler_loop(tasks, inflight: Inflight, stopped: threading.Event) -> None:
    while not stopped.is_set():
        try:
            enqueue_due(tasks, inflight)
        except Exception as error:
            print(f"scheduler failed: {error}")
        stopped.wait(1)


def main() -> None:
    tasks: queue.Queue = queue.Queue()
    results: queue.Queue = queue.Queue()
    inflight = Inflight()
    stopped = threading.Event()
    poller = threading.Thread(
        target=telegram_loop,
        args=(tasks, results, inflight, stopped),
        name="telegram",
        daemon=True,
    )
    scheduler = threading.Thread(
        target=scheduler_loop,
        args=(tasks, inflight, stopped),
        name="scheduler",
        daemon=True,
    )
    poller.start()
    scheduler.start()
    try:
        browser_loop(tasks, results, stopped)
    finally:
        stopped.set()
        poller.join(timeout=5)
        scheduler.join(timeout=5)


if __name__ == "__main__":
    main()
