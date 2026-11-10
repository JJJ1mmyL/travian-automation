import json
import sys

from travian.browser import browser_page
from travian.modules.login import login
from travian.modules.resources import list_fields, read_resource_page, upgrade_field

USAGE = "Use: resources.py [fields | upgrade SLOT [video] [inventory]]"


def split_flags(args: list[str]) -> tuple[list[str], bool, bool]:
    watch = False
    inventory = False
    body = list(args)
    while body and body[-1] in ("video", "inventory"):
        if body[-1] == "video":
            watch = True
        else:
            inventory = True
        body.pop()
    return body, watch, inventory


def main() -> None:
    body, watch, inventory = split_flags(sys.argv[1:])
    if not body:
        action = ("page",)
    elif body == ["fields"]:
        action = ("fields",)
    elif len(body) == 2 and body[0] == "upgrade" and body[1].isdigit():
        action = ("upgrade", int(body[1]), watch, inventory)
    else:
        print(USAGE)
        return

    with browser_page() as page:
        login(page)
        if action[0] == "page":
            result = read_resource_page(page)
        elif action[0] == "fields":
            result = list_fields(page)
        else:
            result = upgrade_field(page, action[1], watch_video=action[2], use_inventory=action[3])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
