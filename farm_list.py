import json

from travian.browser import firefox_page
from travian.modules.farm_list import gold_club_activated, list_farm_lists
from travian.modules.login import login


def main() -> None:
    with browser_page() as page:
        login(page)
        print(
            json.dumps(
                {
                    "gold_club_activated": gold_club_activated(page),
                    "farm_lists": list_farm_lists(page),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
