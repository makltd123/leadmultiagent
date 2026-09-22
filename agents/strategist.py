import asyncio
import json
import logging
from config import groq_client, GROQ_MODEL
from database import save_product_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — эксперт по B2B-продажам. Твоя задача — проанализировать описание продукта и сформулировать критерии поиска потенциальных клиентов в Telegram-чатах.

Отвечай ТОЛЬКО валидным JSON без каких-либо пояснений и markdown-обёрток."""

USER_PROMPT_TEMPLATE = """Описание продукта:
{product_description}

Сформулируй критерии поиска лидов в виде JSON:
{{
  "icp": "строка — кто идеальный клиент (1-2 предложения)",
  "pain_points": ["боль 1", "боль 2", "боль 3"],
  "keywords": ["ключевое слово 1", "слово 2", "слово 3"],
  "intent_signals": ["ищу", "нужен подрядчик", "посоветуйте", "кто делает"],
  "anti_signals": ["продаю", "предлагаю", "ищу работу", "вакансия"],
  "target_categories": ["логистика", "ритейл", "производство"]
}}

Правила:
- keywords: 10-20 слов/фраз напрямую связанных с продуктом
- intent_signals: 5-10 фраз, показывающих что человек ИЩЕТ, а не ПРЕДЛАГАЕТ
- anti_signals: 5-10 фраз, исключающих продавцов, конкурентов, джобсикеров
- target_categories: 3-7 ниш где чаще всего бывают клиенты"""


async def run(product_description: str) -> dict:
    for attempt in range(3):
        try:
            response = await asyncio.wait_for(
                groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                            product_description=product_description
                        )},
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                ),
                timeout=30,
            )
            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)
            result["product_description"] = product_description
            await save_product_config(result)
            logger.info("Strategist: конфиг продукта сохранён")
            return result
        except json.JSONDecodeError as e:
            logger.error("Strategist: ошибка парсинга JSON (попытка %d): %s", attempt + 1, e)
        except Exception as e:
            logger.exception("Strategist: ошибка API (попытка %d)", attempt + 1)
        await asyncio.sleep(2 ** attempt)

    raise RuntimeError("Strategist: не удалось получить ответ после 3 попыток")
