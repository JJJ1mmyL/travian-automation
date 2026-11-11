"""Enqueue due automations and per-chat notification checks."""

import random
import time

from travian.automations import AUTOMATIONS
from travian.notifications import NOTIFICATIONS
from travian.store import load, update


def enqueue_due(tasks, inflight, now: float | None = None) -> None:
    now = time.time() if now is None else now
    config = load()
    for module in AUTOMATIONS.values():
        task = module.run(config, now)
        if task is None:
            continue
        key = f"automation:{module.name}"
        if not inflight.try_acquire(key):
            continue
        auto = config["automations"][module.name]
        low, high = sorted((int(auto["interval_min"]), int(auto["interval_max"])))
        delay = random.randint(low, high)
        when = time.time() + delay

        def mutate(data, clock=module.name, due=when):
            data["clocks"][clock] = due

        update(mutate)
        task["requester"] = {"kind": "automation", "name": module.name}
        task["inflight"] = key
        tasks.put(task)
        print(f"queued {module.name}", flush=True)
    for chat_id in config["allow_chat_ids"]:
        chat_id = str(chat_id)
        for module in NOTIFICATIONS.values():
            task = module.run(config, chat_id, now)
            if task is None:
                continue
            key = f"notification:{module.name}:{chat_id}"
            if not inflight.try_acquire(key):
                continue
            when = time.time() + module.INTERVAL

            def mutate(data, clock=key, due=when):
                data["clocks"][clock] = due

            update(mutate)
            task["requester"] = {"kind": "notification", "name": module.name, "chat_id": chat_id}
            task["inflight"] = key
            tasks.put(task)
            print(f"queued {module.name} for {chat_id}", flush=True)
