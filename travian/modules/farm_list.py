"""Farm list. Check Gold Club, list farm lists, and start them."""

import random
import re
import time

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER

name = "farm_list"

DORF1 = f"{SERVER}/dorf1.php"
FARM_LIST = f"{SERVER}/build.php?id=39&gid=16&tt=99"

# Last-raid icon for a full win with no troop losses (green cross).
SAFE_LAST_RAID = "attack_won_withoutLosses_small"
# Interval encoded in the list title, e.g. "inf (15 mins)" or "spawn rainbow - (5 mins)".
MINS_IN_NAME = re.compile(r"(\d+)\s*mins?", re.IGNORECASE)


def minutes_from_name(list_name: str) -> int | None:
    match = MINS_IN_NAME.search(list_name or "")
    return int(match.group(1)) if match else None


def farm_list_due(farm_list: dict, last_sent: dict, now: float | None = None) -> bool:
    """Send when no interval in the name, never sent, or the named minutes have elapsed."""
    mins = minutes_from_name(farm_list.get("name") or "")
    if mins is None:
        return True
    sent = last_sent.get(str(farm_list["id"]))
    if sent is None:
        return True
    now = time.time() if now is None else now
    return (now - float(sent)) > mins * 60


def _pause(page, low: int = 1, high: int = 3) -> None:
    page.wait_for_timeout(random.randint(low, high) * 1000)


def _read_gold_club(page):
    return page.evaluate(
        """() => {
            const match = document.documentElement.innerHTML.match(/"goldClub":(true|false)/);
            return match ? match[1] : null;
        }"""
    )


def gold_club_activated(page) -> bool:
    """Return True when the account's Gold Club is active."""
    raw = _read_gold_club(page)
    if raw is None:
        page.goto(DORF1, wait_until="domcontentloaded")
        page.locator("#stockBar").wait_for()
        raw = _read_gold_club(page)
    if raw is None:
        raise RuntimeError("Gold Club status was not on the page")
    return raw == "true"


def open_farm_lists(page) -> None:
    if not gold_club_activated(page):
        raise RuntimeError("Gold Club is not activated")
    page.goto(FARM_LIST, wait_until="domcontentloaded")
    page.locator("#rallyPointFarmList").wait_for()


def _ensure_farm_lists(page) -> None:
    if page.locator("#rallyPointFarmList").count() == 0:
        open_farm_lists(page)


def list_farm_lists(page) -> list:
    _ensure_farm_lists(page)
    raw = page.evaluate(
        """() => {
            const script = [...document.scripts].map((node) => node.textContent || "").find((text) => text.includes('"farmLists"'));
            if (!script) return [];
            const marker = "viewData: ";
            const start = script.indexOf(marker);
            if (start < 0) return [];
            let depth = 0;
            let end = start + marker.length;
            for (let index = end; index < script.length; index += 1) {
                const char = script[index];
                if (char === "{") depth += 1;
                else if (char === "}") {
                    depth -= 1;
                    if (depth === 0) {
                        end = index + 1;
                        break;
                    }
                }
            }
            const data = JSON.parse(script.slice(start + marker.length, end));
            const villages = Object.fromEntries((data.ownPlayer.villages || []).map((village) => [village.id, village.name]));
            return (data.ownPlayer.farmLists || []).map((farmList) => ({
                id: farmList.id,
                name: farmList.name,
                slots: farmList.slotsAmount,
                running_raids: farmList.runningRaidsAmount,
                last_started: farmList.lastStartedTime,
                village_id: farmList.ownerVillage ? farmList.ownerVillage.id : null,
                village: farmList.ownerVillage ? villages[farmList.ownerVillage.id] || "" : "",
            }));
        }"""
    )
    return raw


def _is_disabled(button) -> bool:
    classes = (button.get_attribute("class") or "").split()
    return "disabled" in classes


def _slot_id(row) -> str | None:
    checkbox = row.locator('input[name="selectOne"]')
    if checkbox.count() == 0:
        return None
    return checkbox.first.get_attribute("data-slot-id")


def _last_raid_classes(row) -> list[str]:
    icon = row.locator("i.lastRaidState")
    if icon.count() == 0:
        return []
    return (icon.first.get_attribute("class") or "").split()


def _should_deactivate(row) -> bool:
    """Active targets with a last raid that is not without-loss. No last raid → keep."""
    classes = _last_raid_classes(row)
    if not classes:
        return False
    return SAFE_LAST_RAID not in classes


def _next_unsafe_active_row(scope):
    """Return the first active slot whose last raid is not a green without-loss cross."""
    rows = scope.locator("tr.slot:not(.disabled)")
    for index in range(rows.count()):
        row = rows.nth(index)
        if _should_deactivate(row):
            return row
    return None


def _dismiss_context_menu(page) -> None:
    wrapper = page.locator(".contextMenuWrapper")
    if wrapper.count() == 0:
        return
    page.keyboard.press("Escape")
    try:
        wrapper.first.wait_for(state="hidden", timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        page.locator("body").click(position={"x": 5, "y": 5}, force=True)


def _farm_list_wrapper(page, list_id: int):
    return page.locator(f'.farmListWrapper:has([data-list="{list_id}"])')


def _ensure_farm_list_expanded(page, list_id: int) -> bool:
    """Expand a farm list so slot rows (and last-raid icons) are in the DOM."""
    wrapper = _farm_list_wrapper(page, list_id)
    if wrapper.count() == 0:
        return False
    classes = (wrapper.first.get_attribute("class") or "").split()
    if "expanded" in classes:
        return True
    if "collapsed" not in classes:
        return False

    toggle = wrapper.locator("a.expandCollapse")
    if toggle.count() == 0:
        return False
    toggle.first.click(timeout=WAIT_FOR_TIMEOUT_MS)
    _pause(page, 1, 2)
    expanded = page.locator(f'.farmListWrapper.expanded:has([data-list="{list_id}"])')
    try:
        expanded.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return False

    table = expanded.locator("table.slots")
    if table.count() and "noSlots" not in ((table.first.get_attribute("class") or "").split()):
        try:
            expanded.locator("tr.slot").first.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
        except Exception:
            return False
    return True


def _deactivate_row(page, row) -> dict | None:
    slot_id = _slot_id(row)
    if not slot_id:
        return None

    _dismiss_context_menu(page)
    menu = row.locator("td.openContextMenu a")
    if menu.count() == 0:
        return None
    menu.first.click(timeout=WAIT_FOR_TIMEOUT_MS)

    button = page.locator(".contextMenuWrapper button.entry.deactivate")
    if button.count() == 0:
        _dismiss_context_menu(page)
        return None
    button.first.click(timeout=WAIT_FOR_TIMEOUT_MS)

    disabled = page.locator(f'tr.slot.disabled:has(input[data-slot-id="{slot_id}"])')
    try:
        disabled.wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return None
    return {"slot_id": slot_id}


def deactivate_unsafe_active_targets(page, *, list_id: int | None = None) -> dict:
    """Before sending, turn off active targets whose last raid was not without loss."""
    _ensure_farm_lists(page)
    scope = page.locator("#rallyPointFarmList")
    if list_id is not None:
        scope = _farm_list_wrapper(page, list_id)
        if scope.count() == 0:
            return {"deactivated": 0, "targets": [], "reason": "farm list missing"}
        if not _ensure_farm_list_expanded(page, list_id):
            return {"deactivated": 0, "targets": [], "reason": "expand failed"}
        scope = _farm_list_wrapper(page, list_id)

    deactivated = []
    while True:
        row = _next_unsafe_active_row(scope)
        if row is None:
            break
        result = _deactivate_row(page, row)
        if result is None:
            return {
                "deactivated": len(deactivated),
                "targets": deactivated,
                "reason": "deactivate control missing",
            }
        deactivated.append(result)
        _pause(page, 1, 3)

    return {"deactivated": len(deactivated), "targets": deactivated}


def _raids_from_send(payload: dict) -> dict:
    raids_sent = 0
    errors = []
    for farm_list in payload.get("lists") or []:
        if farm_list.get("error"):
            errors.append(farm_list["error"])
        for target in farm_list.get("targets") or []:
            if target.get("error"):
                errors.append(target["error"])
            else:
                raids_sent += 1
    result = {"started": raids_sent > 0, "raids_sent": raids_sent}
    if errors and raids_sent == 0:
        result["reason"] = errors[0]
    return result


def _click_and_count_raids(page, button) -> dict:
    with page.expect_response("**/api/v1/farm-list/send", timeout=5_000) as sent:
        button.click(timeout=5_000)
    return _raids_from_send(sent.value.json())


def start_farm_list(page, *, list_id: int | None = None, name: str | None = None, index: int = 0) -> dict:
    """Start one farm list by id, name, or position. The first list is the default."""
    lists = list_farm_lists(page)
    if list_id is not None:
        chosen = next((item for item in lists if item["id"] == list_id), None)
    elif name is not None:
        chosen = next((item for item in lists if item["name"] == name), None)
    elif 0 <= index < len(lists):
        chosen = lists[index]
    else:
        chosen = None
    if chosen is None:
        return {"started": False, "raids_sent": 0, "reason": "no farm list"}

    pruned = deactivate_unsafe_active_targets(page, list_id=chosen["id"])
    if pruned.get("reason"):
        return {
            "started": False,
            "raids_sent": 0,
            "reason": pruned["reason"],
            "deactivated": pruned.get("deactivated", 0),
            "farm_list": chosen,
        }

    wrapper = page.locator(f'.farmListWrapper:has([data-list="{chosen["id"]}"])')
    button = wrapper.locator(".farmListHeader button.startFarmList")
    if button.count() == 0:
        return {
            "started": False,
            "raids_sent": 0,
            "reason": "start button missing",
            "deactivated": pruned["deactivated"],
            "farm_list": chosen,
        }
    if _is_disabled(button):
        return {
            "started": False,
            "raids_sent": 0,
            "reason": "disabled",
            "deactivated": pruned["deactivated"],
            "farm_list": chosen,
        }

    _pause(page, 1, 2)
    result = _click_and_count_raids(page, button)
    result["farm_list"] = chosen
    result["deactivated"] = pruned["deactivated"]
    return result


def start_due_farm_lists(page, *, last_sent: dict | None = None, now: float | None = None) -> dict:
    """Start each farm list that is due from its name interval and last_sent map."""
    now = time.time() if now is None else now
    last_sent = {str(key): float(value) for key, value in (last_sent or {}).items()}
    lists = list_farm_lists(page)
    started = []
    skipped = []
    raids_sent = 0
    deactivated = 0
    updated_last_sent = dict(last_sent)

    for farm_list in lists:
        key = str(farm_list["id"])
        mins = minutes_from_name(farm_list.get("name") or "")
        if not farm_list_due(farm_list, last_sent, now):
            skipped.append(
                {
                    "farm_list": farm_list,
                    "reason": "not due",
                    "interval_min": mins,
                    "last_sent": last_sent.get(key),
                }
            )
            continue

        pruned = deactivate_unsafe_active_targets(page, list_id=farm_list["id"])
        deactivated += pruned.get("deactivated", 0)
        if pruned.get("reason"):
            skipped.append(
                {
                    "farm_list": farm_list,
                    "reason": pruned["reason"],
                    "interval_min": mins,
                    "last_sent": last_sent.get(key),
                }
            )
            continue

        wrapper = page.locator(f'.farmListWrapper:has([data-list="{farm_list["id"]}"])')
        button = wrapper.locator(".farmListHeader button.startFarmList")
        if button.count() == 0:
            skipped.append({"farm_list": farm_list, "reason": "start button missing", "interval_min": mins})
            continue
        if _is_disabled(button):
            skipped.append({"farm_list": farm_list, "reason": "disabled", "interval_min": mins})
            continue

        _pause(page, 1, 2)
        send = _click_and_count_raids(page, button)
        sent_at = time.time()
        updated_last_sent[key] = sent_at
        raids_sent += send.get("raids_sent", 0)
        started.append(
            {
                "farm_list": farm_list,
                "raids_sent": send.get("raids_sent", 0),
                "reason": send.get("reason"),
                "interval_min": mins,
                "last_sent": sent_at,
            }
        )
        _pause(page, 2, 4)

    result = {
        "started": bool(started),
        "raids_sent": raids_sent,
        "deactivated": deactivated,
        "lists_started": started,
        "lists_skipped": skipped,
        "last_sent": updated_last_sent,
        "farm_lists": lists,
    }
    if not started:
        if skipped and all(item.get("reason") == "not due" for item in skipped):
            result["reason"] = "nothing due"
        elif skipped:
            result["reason"] = skipped[0].get("reason") or "nothing started"
        else:
            result["reason"] = "no farm list"
    return result


def start_all_farm_lists(page) -> dict:
    """Start every list as if none were sent yet (all due)."""
    return start_due_farm_lists(page, last_sent={}, now=time.time())
