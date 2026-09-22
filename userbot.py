import asyncio
import logging
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message

import agents.classifier as classifier
import agents.enricher as enricher
import agents.writer as writer
from config import TG_API_ID, TG_API_HASH, TG_PHONE, KEYWORD_MIN_SCORE
from database import (
    load_product_config, save_market_signal, save_lead, mark_lead_notified
)
from filters import passes_prefilter, keyword_score

logger = logging.getLogger(__name__)

app = Client(
    "session",
    api_id=TG_API_ID,
    api_hash=TG_API_HASH,
    phone_number=TG_PHONE,
)

classifier_queue: asyncio.Queue = asyncio.Queue()
is_monitoring_active = True
_bot_ref = None
_admin_id = None


def set_bot(bot, admin_id: int) -> None:
    global _bot_ref, _admin_id
    _bot_ref = bot
    _admin_id = admin_id


@app.on_message(filters.group & ~filters.bot)
async def handle_message(client: Client, message: Message) -> None:
    if not is_monitoring_active:
        return

    text = message.text or message.caption
    if not text:
        return

    # Парсим упоминания чатов и вступаем по цепочке
    import re
    mentioned = re.findall(r'(?:@|t\.me/)([a-zA-Z][a-zA-Z0-9_]{3,})', text)
    if mentioned:
        import agents.scout as scout
        for username in mentioned:
            asyncio.create_task(scout._try_add_chat_by_username(client, username))

    config = await load_product_config()
    if not config:
        return

    is_bot_sender = message.from_user.is_bot if message.from_user else False
    msg_date = message.date
    if isinstance(msg_date, int):
        msg_date = datetime.utcfromtimestamp(msg_date)

    if not passes_prefilter(text, msg_date, is_bot_sender, config, KEYWORD_MIN_SCORE):
        return

    matched_keywords = [
        kw for kw in config.get("keywords", []) if kw.lower() in text.lower()
    ]
    await save_market_signal({
        "chat_id": message.chat.id,
        "message_text": text[:500],
        "keywords_matched": matched_keywords,
    })

    await classifier_queue.put((message, config))


async def classifier_worker() -> None:
    while True:
        try:
            message, config = await classifier_queue.get()
            await _process_lead_candidate(message, config)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("classifier_worker: необработанная ошибка")
        finally:
            classifier_queue.task_done()


async def _process_lead_candidate(message: Message, config: dict) -> None:
    text = message.text or message.caption or ""
    chat_context = {
        "title": message.chat.title or "",
        "member_count": getattr(message.chat, "members_count", 0) or 0,
    }

    result = await classifier.classify(text, config, chat_context)
    if not result.get("is_lead") or result.get("score", 0) < 0.7:
        return

    logger.info("Лид найден (score=%.2f) в %s", result["score"], message.chat.title)

    sender_id = message.from_user.id if message.from_user else None
    enrichment = {}
    if sender_id:
        enrichment = await enricher.enrich(sender_id, message, app)

    draft = await writer.write_draft(text, enrichment, config)

    chat_username = getattr(message.chat, "username", None)
    msg_url = None
    if chat_username:
        msg_url = f"https://t.me/{chat_username}/{message.id}"

    lead_id = await save_lead({
        "message_id": message.id,
        "chat_id": message.chat.id,
        "chat_title": message.chat.title,
        "sender_id": sender_id,
        "sender_username": enrichment.get("username"),
        "sender_name": enrichment.get("name"),
        "message_text": text,
        "message_url": msg_url,
        "relevance_score": result["score"],
        "relevance_reason": result.get("reason"),
        "enrichment": enrichment,
        "draft_response": draft,
    })

    if _bot_ref and _admin_id:
        await _notify_lead(_bot_ref, _admin_id, lead_id, message, enrichment, result, draft, msg_url)
        await mark_lead_notified(lead_id)


async def _notify_lead(bot, admin_id, lead_id, message, enrichment, classification, draft, msg_url):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    name = enrichment.get("name") or "Неизвестный"
    username = enrichment.get("username") or ""
    company = enrichment.get("company") or "не определена"
    role = enrichment.get("role") or "не определена"
    chat_title = message.chat.title or ""
    member_count = getattr(message.chat, "members_count", 0) or 0
    text = message.text or message.caption or ""
    reason = classification.get("reason", "")

    notification = (
        f"🔥 Новый лид\n\n"
        f"👤 {name} {username}\n"
        f"🏢 Предположительно: {company}\n"
        f"💼 Роль: {role}\n\n"
        f"📍 Чат: {chat_title} ({member_count:,} участников)\n\n"
        f"💬 Сообщение:\n\"{text[:300]}\"\n\n"
        f"🎯 Почему лид: {reason}\n\n"
        f"✏️ Черновик ответа:\n\"{draft}\""
    )

    buttons = [
        [
            InlineKeyboardButton("✅ В работе", callback_data=f"lead_working_{lead_id}"),
            InlineKeyboardButton("❌ Не актуально", callback_data=f"lead_ignored_{lead_id}"),
        ]
    ]
    if msg_url:
        buttons.append([InlineKeyboardButton("🔗 Открыть чат", url=msg_url)])

    markup = InlineKeyboardMarkup(buttons)
    await bot.send_message(chat_id=admin_id, text=notification, reply_markup=markup)


async def join_chats(chat_list: list[str]) -> None:
    import agents.scout as scout
    for username in chat_list:
        await scout._try_join_and_save(app, username)


async def run_userbot() -> None:
    async with app:
        worker_task = asyncio.create_task(classifier_worker())
        logger.info("Userbot запущен, слушаю чаты...")
        await asyncio.Event().wait()
        worker_task.cancel()
