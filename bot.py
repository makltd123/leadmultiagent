import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

import agents.strategist as strategist
from config import BOT_TOKEN, ADMIN_ID
from database import (
    load_product_config, get_recent_leads, get_leads_stats,
    update_lead_status, get_chat_count,
)

logger = logging.getLogger(__name__)

WAITING_PRODUCT_DESCRIPTION = 1


def _admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, context)
    return wrapper


@_admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = await load_product_config()
    if config:
        await update.message.reply_text(
            "Система уже настроена. Используй /setup чтобы изменить продукт.\n"
            "/stats — статистика\n/leads — последние лиды\n/pause /resume — управление мониторингом"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Привет! Опиши что ты продаёшь — продукт, услугу, решение.\n\n"
        "Напиши 2-5 предложений: что делает продукт, кто клиент, какую проблему решает."
    )
    return WAITING_PRODUCT_DESCRIPTION


@_admin_only
async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Опиши новый продукт/услугу. Стратег переформулирует критерии поиска.\n"
        "Библиотека чатов сохранится, поиск по новым критериям начнётся сразу."
    )
    return WAITING_PRODUCT_DESCRIPTION


async def receive_product_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    description = update.message.text
    await update.message.reply_text("Анализирую продукт и формулирую критерии поиска...")

    try:
        config = await strategist.run(description)
        keywords_preview = ", ".join(config.get("keywords", [])[:5])
        await update.message.reply_text(
            f"Готово! Критерии сформулированы.\n\n"
            f"ICP: {config.get('icp', '')[:200]}\n\n"
            f"Ключевые слова ({len(config.get('keywords', []))} шт.): {keywords_preview}...\n\n"
            f"Scout начинает строить библиотеку чатов. Первые лиды могут появиться через час."
        )

        from userbot import app as userbot_app
        import agents.scout as scout
        import asyncio
        asyncio.create_task(scout.run(userbot_app))

    except Exception as e:
        logger.exception("Ошибка Strategist")
        await update.message.reply_text(f"Ошибка при настройке: {e}")

    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


@_admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = await get_leads_stats()
    chat_count = await get_chat_count()
    config = await load_product_config()
    product = config.get("product_description", "не настроен")[:100] if config else "не настроен"

    text = (
        f"📊 Статистика\n\n"
        f"Продукт: {product}\n\n"
        f"Чатов в мониторинге: {chat_count}\n"
        f"Лидов сегодня: {stats['today']}\n"
        f"Лидов за неделю: {stats['week']}"
    )
    await update.message.reply_text(text)


@_admin_only
async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    leads = await get_recent_leads(10)
    if not leads:
        await update.message.reply_text("Лидов пока нет.")
        return

    status_emoji = {
        "new": "🆕", "notified": "📬", "working": "🔨",
        "closed": "✅", "ignored": "❌",
    }

    lines = []
    for lead in leads:
        emoji = status_emoji.get(lead.get("status", "new"), "•")
        name = lead.get("sender_name") or lead.get("sender_username") or "Неизвестный"
        chat = lead.get("chat_title") or ""
        score = lead.get("relevance_score", 0)
        lines.append(f"{emoji} {name} | {chat} | score={score:.2f}")

    await update.message.reply_text("Последние 10 лидов:\n\n" + "\n".join(lines))


@_admin_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import userbot
    userbot.is_monitoring_active = False
    await update.message.reply_text("⏸ Мониторинг приостановлен.")


@_admin_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import userbot
    userbot.is_monitoring_active = True
    await update.message.reply_text("▶️ Мониторинг возобновлён.")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        return

    await query.answer()
    data = query.data

    if data.startswith("lead_working_"):
        lead_id = int(data.split("_")[-1])
        await update_lead_status(lead_id, "working")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ Лид #{lead_id} взят в работу. Напомню через 3 дня.",
        )
        context.job_queue.run_once(
            _remind_lead,
            when=timedelta(days=3),
            data={"lead_id": lead_id, "chat_id": query.message.chat_id},
        )

    elif data.startswith("lead_ignored_"):
        lead_id = int(data.split("_")[-1])
        await update_lead_status(lead_id, "ignored")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ Лид #{lead_id} отмечен как нерелевантный.")


async def _remind_lead(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    lead_id = data["lead_id"]
    chat_id = data["chat_id"]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ Напоминание: лид #{lead_id} в работе уже 3 дня. Как продвигается?",
    )


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("setup", cmd_setup),
        ],
        states={
            WAITING_PRODUCT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_product_description),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app


async def run_bot() -> None:
    application = build_application()
    import userbot
    userbot.set_bot(application.bot, ADMIN_ID)

    logger.info("Бот уведомлений запущен")
    async with application:
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()
        await application.updater.stop()
        await application.stop()


import asyncio
