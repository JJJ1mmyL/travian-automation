"""Farm list. Check Gold Club, list farm lists, and start them."""

from travian.config import SERVER

name = "farm_list"

DORF1 = f"{SERVER}/dorf1.php"
FARM_LIST = f"{SERVER}/build.php?id=39&gid=16&tt=99"


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

    wrapper = page.locator(f'.farmListWrapper:has([data-list="{chosen["id"]}"])')
    button = wrapper.locator(".farmListHeader button.startFarmList")
    if button.count() == 0:
        return {"started": False, "raids_sent": 0, "reason": "start button missing", "farm_list": chosen}
    if _is_disabled(button):
        return {"started": False, "raids_sent": 0, "reason": "disabled", "farm_list": chosen}

    result = _click_and_count_raids(page, button)
    result["farm_list"] = chosen
    return result


def start_all_farm_lists(page) -> dict:
    _ensure_farm_lists(page)
    button = page.locator("button.startAllFarmLists")
    if button.count() == 0:
        return {"started": False, "raids_sent": 0, "reason": "start button missing"}
    if _is_disabled(button):
        return {"started": False, "raids_sent": 0, "reason": "disabled"}
    result = _click_and_count_raids(page, button)
    result["farm_lists"] = list_farm_lists(page)
    return result
