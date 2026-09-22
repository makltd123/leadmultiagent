import asyncio
import logging
from config import nvidia_client, NVIDIA_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты пишешь первое сообщение потенциальному клиенту от имени живого человека.

Правила:
- Максимум 3-4 предложения
- Первое предложение — прямой отклик на конкретный запрос
- Никакого "предлагаем", "наш продукт", "хотели бы", "компания"
- Заканчивается одним коротким вопросом или "актуально?"
- Тон: равный к равному, коллега коллеге
- Без шаблонов, без официоза, без восклицательных знаков
- Обращение по имени если есть"""

USER_PROMPT_TEMPLATE = """Что продаёт отправитель: {product_description}

Запрос лида:
{lead_message}

Информация о лиде:
Имя: {name}
Компания: {company}
Роль: {role}
Резюме: {summary}

Напиши черновик ответа:"""


async def write_draft(lead_message: str, enrichment: dict, product_config: dict) -> str:
    prompt = USER_PROMPT_TEMPLATE.format(
        product_description=product_config.get("product_description", "")[:300],
        lead_message=lead_message[:400],
        name=enrichment.get("name") or "не известно",
        company=enrichment.get("company") or "не известно",
        role=enrichment.get("role") or "не известно",
        summary=enrichment.get("summary") or "",
    )

    for attempt in range(3):
        try:
            response = await nvidia_client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.exception("Writer: ошибка API (попытка %d)", attempt + 1)
        await asyncio.sleep(2 ** attempt)

    return "Черновик недоступен — ошибка API."
