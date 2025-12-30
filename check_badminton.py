import os
import smtplib
from email.mime.text import MIMEText
import asyncio
import re
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

        # 施設リストの設定
        # filter_time: True = 三橋ルール（平日19-21時のみ）、False = 全時間帯
        targets = [
            {"name": "鈴谷公民館", "room": "多目的ホール", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室", "filter": True},
            {"name": "浦和西体育館", "room": "競技場", "filter": True},
            {"name": "与野体育館", "room": "競技場", "filter": True},
            {"name": "大宮体育館", "room": "競技場", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場１／２", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ１／２", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            calendar_table = page.locator("table.cal_table")
            if await calendar_table.count() == 0: return

            month_label = page.locator("td.cal_month, .cal_month_area")
            month_text = await month_label.first.inner_text() if await month_label.count() > 0 else ""
            month_text = month_text.strip().replace("\n", "")

            cells = calendar_table.locator("td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                if await cell.locator("img[alt*='空き']").count() > 0:
                    day_text = await cell.locator(".cal_day").inner_text()
                    
                    # 土日祝判定
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    if not filter_time or is_weekend:
                        found_vacancies.append(f"【{facility_name}】{month_text}{day_text}に空きあり")
                    else:
                        # 平日の時間指定チェック
                        await cell.locator("a").first.click()
                        await asyncio.sleep(1)
                        if await page.locator("tr", has_text="19:00").locator("img[alt*='空き']").count() > 0:
                            found_vacancies.append(f"【{facility_name}】{month_text}{day_text} 19-21時に空きあり！")
                        await page.get_by_role("link", name="もどる").click()
                        await asyncio.sleep(1)

        # 巡回開始
        for target in targets:
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/")
                await page.get_by_role("link", name="施設の空き状況").click()
                await page.get_by_role("link", name="利用目的から").click()
                await page.get_by_role("link", name="屋内スポーツ").click()
                await page.get_by_role("link", name="バドミントン").click()

                # 施設名をクリック
                await page.get_by_role("link", name=re.compile(target['name'])).click()
                
                # 部屋名があればクリック（三橋やアリーナなど複数ある場合用）
                room_link = page.get_by_role("link", name=re.compile(target['room']))
                if await room_link.count() > 0:
                    await room_link.first.click()

                # 3ヶ月分チェック
                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    await page.get_by_role("link", name="次の月").click()
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"{target['name']} の巡回中にスキップ: {e}")

        # 結果送信
        if found_vacancies:
            send_email("【予約空き速報】バドミントン全施設", "\n".join(found_vacancies))

        await context.close()
        await browser.close()

def send_email(subject, body):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    with smtplib.SMTP("smtp.mail.me.com", 587) as server:
        server.starttls()
        server.login(SENDER_EMAIL, app_password)
        server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())

if __name__ == "__main__":
    asyncio.run(run())
