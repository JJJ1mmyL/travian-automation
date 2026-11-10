import json

from travian.browser import firefox_page
from travian.modules.adventures import (
    hero_status,
    list_adventures,
    open_adventures,
    video_switches,
    watch_video,
)
from travian.modules.login import login


def main() -> None:
    with browser_page() as page:
        login(page)
        open_adventures(page)
        switches = video_switches(page)
        watched = [watch_video(page, item["kind"]) for item in switches if item["ready"]]
        print(
            json.dumps(
                {
                    "url": page.url,
                    "hero": hero_status(page),
                    "adventures": list_adventures(page),
                    "video_switches": video_switches(page),
                    "watched": watched,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
