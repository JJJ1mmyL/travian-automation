import json

from travian.browser import firefox_page
from travian.modules.login import login


def main() -> None:
    with browser_page() as page:
        print(json.dumps(login(page), indent=2))


if __name__ == "__main__":
    main()
