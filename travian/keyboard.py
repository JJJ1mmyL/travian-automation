"""Inline keyboard rows for Telegram."""


def button(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def grid(pairs: list[tuple[str, str]], width: int = 2) -> list:
    buttons = [button(text, data) for text, data in pairs]
    return [buttons[index : index + width] for index in range(0, len(buttons), width)]


def with_home(rows: list) -> list:
    return [*rows, [button("Home", "m:home")]]
