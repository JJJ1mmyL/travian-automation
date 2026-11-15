"""Farm list. Check Gold Club, list farm lists, and start them."""

import random

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER

name = "farm_list"

DORF1 = f"{SERVER}/dorf1.php"
FARM_LIST = f"{SERVER}/build.php?id=39&gid=16&tt=99"

# Last-raid icon for a full win with no troop losses (green cross).
SAFE_LAST_RAID = "attack_won_withoutLosses_small"


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
        scope = page.locator(f'.farmListWrapper:has([data-list="{list_id}"])')
        if scope.count() == 0:
            return {"deactivated": 0, "targets": [], "reason": "farm list missing"}

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


def start_all_farm_lists(page) -> dict:
    _ensure_farm_lists(page)
    pruned = deactivate_unsafe_active_targets(page)
    if pruned.get("reason"):
        return {
            "started": False,
            "raids_sent": 0,
            "reason": pruned["reason"],
            "deactivated": pruned.get("deactivated", 0),
        }

    button = page.locator("button.startAllFarmLists")
    if button.count() == 0:
        return {
            "started": False,
            "raids_sent": 0,
            "reason": "start button missing",
            "deactivated": pruned["deactivated"],
        }
    if _is_disabled(button):
        return {
            "started": False,
            "raids_sent": 0,
            "reason": "disabled",
            "deactivated": pruned["deactivated"],
        }

    _pause(page, 1, 2)
    result = _click_and_count_raids(page, button)
    result["farm_lists"] = list_farm_lists(page)
    result["deactivated"] = pruned["deactivated"]
    return result
