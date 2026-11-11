"""Town hall celebrations. The preset uses the small celebration."""

import re

from travian.browser import WAIT_FOR_TIMEOUT_MS
from travian.config import SERVER


def start_small(page) -> dict:
    """Start one small celebration. The line is done once this has started."""
    page.goto(f"{SERVER}/build.php?gid=24", wait_until="domcontentloaded")
    try:
        page.locator("#build").wait_for(timeout=WAIT_FOR_TIMEOUT_MS)
    except Exception:
        return {"started": False, "reason": "no town hall"}
    clicked = page.evaluate(
        """() => {
            const forms = [...document.querySelectorAll('#build form')];
            const form = forms.find((item) => {
                const type = item.querySelector('[name="type"]');
                return type && String(type.value) === '1';
            });
            if (!form) return 'missing';
            const button = [...form.querySelectorAll('button')].find((node) => !node.disabled && !node.classList.contains('disabled'));
            if (!button) return 'disabled';
            button.click();
            return 'ok';
        }"""
    )
    if clicked != "ok":
        button = page.get_by_role("button", name=re.compile(r"small celebration", re.I))
        if button.count() == 0:
            reason = "not enough resources" if clicked == "disabled" else "no small celebration"
            return {"started": False, "reason": reason}
        if "disabled" in (button.first.get_attribute("class") or ""):
            return {"started": False, "reason": "not enough resources"}
        button.first.click()
    confirm = page.locator(".dialogWrapper button.dialogButtonOk")
    try:
        confirm.click(timeout=3000)
    except Exception:
        pass
    return {"started": True, "reason": ""}
