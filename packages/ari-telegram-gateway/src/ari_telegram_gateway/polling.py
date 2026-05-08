from __future__ import annotations

import argparse
import sys
from typing import Any

from ari_surface_status import SurfaceStatusStore, surface_status_from_telegram_event

from ari_telegram_gateway.asset_saver import TelegramAssetSaver
from ari_telegram_gateway.career_commands import handle_career_command_result
from ari_telegram_gateway.config import TelegramGatewayConfig
from ari_telegram_gateway.event_builder import TelegramEventBuilder
from ari_telegram_gateway.models import AgentRole, TelegramInboundEvent
from ari_telegram_gateway.persistence import TelegramEventStore, TelegramPollingStateStore
from ari_telegram_gateway.telegram_client import TelegramBotClient


def run_polling(
    *,
    config: TelegramGatewayConfig,
    client: TelegramBotClient,
    max_updates: int | None = None,
) -> None:
    if max_updates is not None and max_updates <= 0:
        return

    bot = client.get_me()
    builder = TelegramEventBuilder(
        bot_identity=config.bot_identity,
        authorized_telegram_user_id=config.authorized_telegram_user_id,
        bot_id=_optional_str(bot.get("id")),
        bot_username=_optional_str(bot.get("username")),
    )
    store = TelegramEventStore(inbox_dir=config.inbox_dir, events_dir=config.events_dir)
    surface_status_store = SurfaceStatusStore()
    state_store = TelegramPollingStateStore(config.polling_state_file)
    state = state_store.load(bot_identity=config.bot_identity)
    asset_saver = TelegramAssetSaver(events_dir=config.events_dir, telegram_client=client)
    offset = (
        state.last_processed_update_id + 1
        if state is not None and state.last_processed_update_id is not None
        else None
    )
    last_processed_update_id = state.last_processed_update_id if state is not None else None
    seen = 0

    while True:
        updates = client.get_updates(offset=offset, timeout=config.polling_timeout_seconds)
        for update in updates:
            update_id = _optional_int(update.get("update_id"))
            if update_id is not None:
                offset = update_id + 1
            seen += 1

            if update_id is not None and _already_processed(
                update_id,
                last_processed_update_id=last_processed_update_id,
                store=store,
            ):
                state = state_store.save_processed_update(
                    update_id=update_id,
                    bot_identity=config.bot_identity,
                )
                last_processed_update_id = state.last_processed_update_id
                if max_updates is not None and seen >= max_updates:
                    return
                continue

            event = _process_update(
                update,
                builder=builder,
                store=store,
                asset_saver=asset_saver,
                surface_status_store=surface_status_store,
            )
            _send_confirmation(client, event, surface_status_store=surface_status_store)
            if update_id is not None:
                state = state_store.save_processed_update(
                    update_id=update_id,
                    bot_identity=config.bot_identity,
                )
                last_processed_update_id = state.last_processed_update_id
            if max_updates is not None and seen >= max_updates:
                return


def _already_processed(
    update_id: int,
    *,
    last_processed_update_id: int | None,
    store: TelegramEventStore,
) -> bool:
    if last_processed_update_id is not None and update_id <= last_processed_update_id:
        return True
    return store.has_processed_update(update_id)


def _process_update(
    update: dict[str, Any],
    *,
    builder: TelegramEventBuilder,
    store: TelegramEventStore,
    asset_saver: TelegramAssetSaver,
    surface_status_store: SurfaceStatusStore | None = None,
) -> TelegramInboundEvent:
    store.save_raw_update(update)
    event = builder.build_from_update(update)
    if event.authorized:
        event = asset_saver.save_assets(event)
        if event.pending_codex_task is not None:
            store.save_codex_task(event.pending_codex_task, event_id=event.event_id)
    store.save_event(event)
    if surface_status_store is not None:
        surface_status_store.write(surface_status_from_telegram_event(event))
    return event


def _send_confirmation(
    client: TelegramBotClient,
    event: TelegramInboundEvent,
    *,
    surface_status_store: SurfaceStatusStore | None = None,
) -> None:
    if not event.conversation_id:
        return
    if not event.authorized:
        client.send_message(chat_id=event.conversation_id, text="ARI rejected this sender.")
        return
    client.send_message(
        chat_id=event.conversation_id,
        text=_confirmation_text(event, surface_status_store=surface_status_store),
    )


def _confirmation_text(
    event: TelegramInboundEvent,
    *,
    surface_status_store: SurfaceStatusStore | None = None,
) -> str:
    career_response = handle_career_command_result(event.raw_text, event_id=event.event_id)
    if career_response is not None:
        if surface_status_store is not None:
            surface_status_store.write(career_response.surface_status)
        return career_response.text

    lines = [
        "ARI received this.",
        f"Role: {event.assigned_role.value}",
        f"Intent: {event.normalized_intent.value}",
        f"Next: {event.next_action}",
    ]
    if event.assigned_role is AgentRole.CTO_CODEX:
        lines.append("Approval required before Codex execution.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ARI Telegram Gateway polling intake.")
    parser.add_argument(
        "--max-updates",
        type=int,
        default=None,
        help="Process at most this many updates. Useful for smoke runs.",
    )
    args = parser.parse_args(argv)
    try:
        config = TelegramGatewayConfig.from_env()
        client = TelegramBotClient(config.telegram_bot_token)
        run_polling(config=config, client=client, max_updates=args.max_updates)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ari-telegram-gateway failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
