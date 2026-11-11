"""Progressive tasks: collect a reward that is ready on the tasks page."""

import random
import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER
from travian.modules.login import dismiss_cookies

name = "tasks"

TABS = ("village", "general")
READY = "#tasks .task.achieved button.collect:not(.disabled):not(.collected)"


def clean_text(text: str) -> str:
    cleaned = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _pause(page, low: int, high: int) -> None:
    page.wait_for_timeout(random.randint(low, high) * 1000)


def _open_tab(page, tab: str) -> str:
    page.goto(f"{SERVER}/tasks?t={tab}", wait_until="domcontentloaded")
    try:
        page.locator("#tasks").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return "tasks page did not open"
    dismiss_cookies(page)
    return ""


def _describe(button) -> dict:
    card = button.locator("xpath=ancestor::div[contains(@class,'task')][1]")
    title = clean_text(card.locator(".title").inner_text()) or "Task"
    amounts = [clean_text(text) for text in card.locator(".rewards span").all_inner_texts()]
    return {
        "title": title,
        "resources": amounts[0] if amounts else "",
        "xp": amounts[1] if len(amounts) > 1 else "",
    }


def _cleared(page, title: str) -> None:
    page.wait_for_function(
        """(title) => {
            const clean = (value) => (value || '')
                .replace(/[\\u202a-\\u202e\\u2066-\\u2069]/g, '')
                .replace(/\\s+/g, ' ')
                .trim();
            return ![...document.querySelectorAll('#tasks .task.achieved .title')]
                .some((el) => clean(el.innerText) === title);
        }""",
        arg=title,
        timeout=WAIT_FOR_TIMEOUT_MS,
    )


def _collect_visible(page) -> tuple[list, list]:
    collected = []
    failed = []
    skipped = set()
    clicked = False
    while True:
        buttons = page.locator(READY)
        choice = None
        for index in range(buttons.count()):
            button = buttons.nth(index)
            info = _describe(button)
            if info["title"] in skipped:
                continue
            choice = (button, info)
            break
        if choice is None:
            break
        if clicked:
            _pause(page, 3, 8)
        button, info = choice
        try:
            button.click()
            _cleared(page, info["title"])
        except Exception:
            failed.append({**info, "reason": "collect did not finish"})
            skipped.add(info["title"])
            clicked = True
            continue
        collected.append(info)
        clicked = True
    return collected, failed


def _each_page(page):
    count = page.locator("#tasks button.page").count()
    if count == 0:
        yield
        return
    for index in range(count):
        page.locator("#tasks button.page").nth(index).evaluate("el => el.click()")
        _pause(page, 2, 5)
        yield


def collect_rewards(page) -> dict:
    collected = []
    failed = []
    for tab in TABS:
        reason = _open_tab(page, tab)
        if reason:
            failed.append({"title": f"{tab} tasks", "reason": reason})
            continue
        for _ in _each_page(page):
            got, missed = _collect_visible(page)
            collected.extend(got)
            failed.extend(missed)
    return {"action": "collect", "collected": collected, "failed": failed}
