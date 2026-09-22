import asyncio
import json
import logging
from config import groq_client, GROQ_MODEL

logger = logging.getLogger(__name__)

_semaphore = asyncio.Semaphore(10)

SYSTEM_PROMPT = """Ты — классификатор B2B-лидов. Определи, является ли сообщение потенциальным лидом для продукта.
Отвечай ТОЛЬКО валидным JSON без пояснений."""

USER_PROMPT_TEMPLATE = """Продукт/ICP: {icp}
Ключевые слова: {keywords}
Сигналы намерения: {intent_signals}
Антисигналы: {anti_signals}

Чат: {chat_title} ({member_count} участников)
Сообщение: {message_text}

Это лид? Ответь JSON:
{{"is_lead": true/false, "score": 0.0-1.0, "reason": "краткое объяснение"}}

score >= 0.7 = явный лид (человек активно ищет)
score 0.5-0.69 = слабый лид
score < 0.5 = не лид"""


async def classify(message_text: str, config: dict, chat_context: dict) -> dict:
    prompt = USER_PROMPT_TEMPLATE.format(
        icp=config.get("icp", ""),
        keywords=", ".join(config.get("keywords", [])),
        intent_signals=", ".join(config.get("intent_signals", [])),
        anti_signals=", ".join(config.get("anti_signals", [])),
        chat_title=chat_context.get("title", ""),
        member_count=chat_context.get("member_count", 0),
        message_text=message_text[:500],
    )

    for attempt in range(3):
        try:
            async with _semaphore:
                response = await groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=128,
                )
            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)
            return result
        except json.JSONDecodeError as e:
            logger.error("Classifier: ошибка парсинга JSON (попытка %d): %s", attempt + 1, e)
        except Exception as e:
            logger.exception("Classifier: ошибка API (попытка %d)", attempt + 1)
        await asyncio.sleep(2 ** attempt)

    return {"is_lead": False, "score": 0.0, "reason": "ошибка классификации"}
