import os
import smtplib
from email.mime.text import MIMEText
import asyncio
import re
import random
from playwright.async_api import async_playwright

# --- 設定エリア ---
RECIPIENT_EMAIL = "badmintonkingdom@icloud.com"
SENDER_EMAIL = "badmintonkingdom@icloud.com"

async def run():
    async with async_playwright() as p:
        # 動作をあえて遅くする(slow_mo)設定を追加
        browser = await p.chromium.launch(headless=True, slow_mo=100)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(90000)

        found_vacancies = []

        # 巡回対象（岩槻は削除済み）
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "鈴谷公民館", "room": "多目的", "filter": False},
            {"name": "浦和駒場体育館", "room": "競技場|第", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ", "filter": True}
        ]

        async def check_calendar_page(facility_name, filter_time):
            # カレンダーが表示されるまで「人間が待つように」じっと待機
            try:
                await page.wait_for_selector("table.cal_table", timeout=45000, state="visible")
                await asyncio.sleep(random.uniform(2, 4)) # 読み込み待ちの遊び
            except:
                print(f"    ! {facility_name}: カレンダー画面の表示を待機中にタイムアウトしました。")
                return

            month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
            month_text = month_text.strip().replace("\n", "")

            cells = page.locator("table.cal_table td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                # △(一部空き)や○(空き)を検知
                img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                if await img.count() > 0:
                    alt = await img.first.get_attribute("alt")
                    day = await cell.locator(".cal_day").inner_text()
                    
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    if not filter_time or is_weekend:
                        found_vacancies.append(f"【{facility_name}】{month_text}{day}日({alt})")
                        print(f"  [発見] {facility_name} {day}日: {alt}")

        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                
                # 人間が操作するように、ゆっくりクリックして進む
                for step in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    await page.get_by_role("link", name=step).click()
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                # 施設名のリンクをクリック
                await page.get_by_role("link", name=re.compile(target['name'])).first.click()
                await asyncio.sleep(2)
                
                # 部屋名のリンクをクリック
                keywords = target['room'].split('|')
                found_room = False
                for kw in keywords:
                    room_link = page.locator(f"a:has-text('{kw}')").first
                    if await room_link.count() > 0:
                        await room_link.click()
                        found_room = True
                        break
                
                if not found_room:
                    print(f"    ! 部屋が見つかりませんでした。")
                    continue

                for _ in range(3):
                    await check_calendar_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await asyncio.sleep(random.uniform(2, 4))
                    else:
                        break
            except Exception as e:
                print(f"    ! エラーにより中断: {target['name']}")
                continue

        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件の空きを見つけました。")
        else:
            print("条件に合う空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き(△)を発見！"
    body = "スクール運営用：以下の空き枠が見つかりました。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    try:
        with smtplib.SMTP("smtp.mail.me.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
    except: pass

if __name__ == "__main__":
    asyncio.run(run())
