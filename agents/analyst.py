import asyncio
import json
import logging
from collections import Counter

from config import nvidia_client, NVIDIA_MODEL
from database import get_signals_last_7_days, get_recent_leads, get_chat_count

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — аналитик B2B-рынка. Проанализируй данные мониторинга Telegram за неделю и выдели ключевые инсайты.
Отвечай ТОЛЬКО валидным JSON без пояснений."""

ANALYSIS_PROMPT = """Сигналы рынка за 7 дней ({count} сообщений):

{signals_sample}

Сформируй JSON:
{{
  "top_pains": [
    {{"text": "описание боли", "count": число}},
    {{"text": "описание боли", "count": число}},
    {{"text": "описание боли", "count": число}}
  ],
  "active_niches": [
    {{"niche": "название", "signals": число}}
  ],
  "competitors_mentioned": [
    {{"name": "конкурент", "count": число, "negative": число}}
  ],
  "insights": "2-3 предложения главных инсайтов недели"
}}"""


async def run_weekly_digest(bot, admin_id: int) -> None:
    try:
        signals = await get_signals_last_7_days()
        leads = await get_recent_leads(100)
        chat_count = await get_chat_count()

        total_signals = len(signals)
        total_leads = len([l for l in leads if l.get("created_at", "").startswith(
            __import__("datetime").datetime.utcnow().strftime("%Y")
        )])

        leads_by_status = Counter(l.get("status", "new") for l in leads)

        signals_sample = "\n".join(
            s["message_text"][:150] for s in signals[:50]
        )

        analysis = {"top_pains": [], "active_niches": [], "competitors_mentioned": [], "insights": ""}

        if signals:
            for attempt in range(3):
                try:
                    response = await nvidia_client.chat.completions.create(
                        model=NVIDIA_MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": ANALYSIS_PROMPT.format(
                                count=total_signals,
                                signals_sample=signals_sample,
                            )},
                        ],
                        temperature=0.3,
                        max_tokens=512,
                    )
                    raw = response.choices[0].message.content.strip()
                    analysis = json.loads(raw)
                    break
                except Exception:
                    logger.exception("Analyst: ошибка API (попытка %d)", attempt + 1)
                    await asyncio.sleep(2 ** attempt)

        top_pains = "\n".join(
            f"{i+1}. \"{p['text']}\" — {p['count']} упоминаний"
            for i, p in enumerate(analysis.get("top_pains", [])[:3])
        ) or "данных недостаточно"

        active_niches = "\n".join(
            f"— {n['niche']} ({n['signals']} сигналов)"
            for n in analysis.get("active_niches", [])[:5]
        ) or "—"

        working = leads_by_status.get("working", 0)

        digest = (
            f"📊 Дайджест за неделю\n\n"
            f"Мониторинг: {chat_count} чатов\n"
            f"Сообщений обработано: {total_signals:,}\n"
            f"Лидов найдено: {len(leads)}\n\n"
            f"🔥 Топ боли рынка:\n{top_pains}\n\n"
            f"📍 Активные ниши:\n{active_niches}\n\n"
            f"Лидов в работе: {working}\n"
            f"Закрыто сделок: отметь сам в боте\n\n"
        )

        if analysis.get("insights"):
            digest += f"💡 Инсайты:\n{analysis['insights']}"

        await bot.send_message(chat_id=admin_id, text=digest)
        logger.info("Analyst: дайджест отправлен")

    except Exception:
        logger.exception("Analyst: ошибка формирования дайджеста")
