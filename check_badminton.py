import os
import smtplib
from email.mime.text import MIMEText
import asyncio
from playwright.async_api import async_playwright

# --- 設定エリア ---
RECIPIENT_EMAIL = "badmintonkingdom@icloud.com"
SENDER_EMAIL = "badmintonkingdom@icloud.com"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        found_vacancies = []

        async def check_current_page(facility_name):
            calendar_table = page.locator("table.cal_table")
            if await calendar_table.count() > 0:
                vacant_icons = calendar_table.locator("img[alt*='空き']")
                count = await vacant_icons.count()
                if count > 0:
                    month_label = page.locator("td.cal_month, .cal_month_area")
                    month_text = await month_label.first.inner_text() if await month_label.count() > 0 else "不明な月"
                    found_vacancies.append(f"【{facility_name}】{month_text.strip()}に {count} 件の空きがあります")

        try:
            await page.goto("https://saitama.rsv.ws-scs.jp/web/")
            await page.get_by_role("link", name="施設の空き状況").click()
            await page.get_by_role("link", name="利用目的から").click()
            await page.get_by_role("link", name="屋内スポーツ").click()
            await page.get_by_role("link", name="バドミントン").click()

            # 1. 鈴谷公民館
            await page.get_by_role("link", name="鈴谷公民館", exact=True).click()
            await page.get_by_role("link", name="鈴谷公民館 多目的ホール（２００人）", exact=True).click()
            for _ in range(4):
                await check_current_page("鈴谷公民館 多目的ホール")
                await page.get_by_role("link", name="次の月").click()
                await asyncio.sleep(1)

            # 2. 岸町公民館
            await page.get_by_role("link", name="もどる").click()
            await page.get_by_role("link", name="もどる").click()
            await page.get_by_role("link", name="岸町公民館").click()
            for _ in range(4):
                await check_current_page("岸町公民館 体育館")
                await page.get_by_role("link", name="次の月").click()
                await asyncio.sleep(1)

            if found_vacancies:
                report = "以下の空きが見つかりました！\n\n" + "\n".join(found_vacancies)
                send_email("【予約空き速報】バドミントン施設", report)
                print("空きを発見！メールを送りました。")
            else:
                print("空きはありませんでした。")

        except Exception as e:
            print(f"エラーが発生しました: {e}")
        finally:
            await context.close()
            await browser.close()

def send_email(subject, body):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    try:
        with smtplib.SMTP("smtp.mail.me.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    asyncio.run(run())
