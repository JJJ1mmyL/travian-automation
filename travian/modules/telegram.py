"""Send a Telegram message through the bot API."""

import json
import os
import ssl
import urllib.request

import certifi

API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _chat_id(chat_id: str | None) -> str:
    chosen = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chosen:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")
    return chosen


def _call(method: str, payload: dict, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        API.format(token=_token(), method=method),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        body = json.load(response)
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or "Telegram request failed")
    return body["result"]


def send_message(text: str, chat_id: str | None = None, buttons: list | None = None) -> dict:
    payload = {"chat_id": _chat_id(chat_id), "text": text}
    if buttons is not None:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    result = _call("sendMessage", payload)
    return {"message_id": result["message_id"], "chat_id": result["chat"]["id"]}


def edit_message(chat_id: str, message_id: int, text: str, buttons: list | None = None) -> dict:
    payload = {"chat_id": _chat_id(chat_id), "message_id": message_id, "text": text}
    if buttons is not None:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    result = _call("editMessageText", payload)
    return {"message_id": result["message_id"], "chat_id": result["chat"]["id"]}


def delete_message(chat_id: str, message_id: int) -> None:
    _call("deleteMessage", {"chat_id": _chat_id(chat_id), "message_id": message_id})


def answer_callback(callback_id: str, text: str = "") -> None:
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    _call("answerCallbackQuery", payload)


def get_updates(offset: int | None = None, timeout: int = 30) -> list:
    payload = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    return _call("getUpdates", payload, timeout=timeout + 10)
