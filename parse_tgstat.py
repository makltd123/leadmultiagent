"""
Парсит tgstat.ru через реальный браузер (Playwright).
Сохраняет username'ы в tgstat_chats.txt
"""
import asyncio
from playwright.async_api import async_playwright

CATEGORIES = ["business"]  # сначала одна категория для теста

async def main():
    usernames = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        for cat in CATEGORIES:
            try:
                url = f"https://tgstat.ru/chats/{cat}"
                print(f"Парсю {url}...")
                await page.goto(url, timeout=15000)
                await page.wait_for_timeout(3000)

                links = await page.query_selector_all("a[href*='t.me/']")
                for link in links:
                    href = await link.get_attribute("href")
                    if href and "t.me/" in href:
                        username = href.split("t.me/")[-1].strip("/").split("?")[0]
                        if username and username.replace("_", "").isalnum():
                            usernames.add(username)

                print(f"  Всего найдено: {len(usernames)}")
                await page.wait_for_timeout(2000)

            except Exception as e:
                print(f"  Ошибка {cat}: {e}")

        await browser.close()

    with open("tgstat_chats.txt", "w", encoding="utf-8") as f:
        for u in sorted(usernames):
            f.write(u + "\n")

    print(f"\nГотово. Сохранено {len(usernames)} username'ов в tgstat_chats.txt")

asyncio.run(main())
