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
        # ステルス性を高めるため、あえて少し動作を遅くする
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        # タイムアウトを極限の180秒(3分)に延長
        page.set_default_timeout(180000)

        found_vacancies = []

        # 巡回対象（岩槻文化公園は除外済み）
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

        async def force_click(selector):
            """標準のclickが効かない時のための強制実行関数"""
            try:
                # Playwrightのクリックではなく、ブラウザ内のJSで直接クリック
                await page.evaluate(f"document.querySelector(\"{selector}\").click()")
            except:
                # セレクターが複雑な場合は通常のclick(force=True)を試す
                await page.locator(selector).first.click(force=True)

        async def check_calendar_page(facility_name, filter_time):
            print(f"    ...カレンダーの読み込みを確認中 ({facility_name})")
            try:
                # 表が出るまで最大60秒待機
                await page.wait_for_selector("table.cal_table", timeout=60000, state="attached")
                await asyncio.sleep(random.uniform(2, 4))
            except:
                # 失敗した場合、今のURLとタイトルをログに出して原因を探る
                title = await page.title()
                print(f"    ! 失敗時のページ: {title}")
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
                        print(f"  [★発見] {facility_name} {day}日: {alt}")

        for target in targets:
            print(f">>> {target['name']} を開始...")
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                
                # 各ステップで「確実に」画面が変わるまで待つ
                for step in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    btn = page.get_by_role("link", name=step)
                    await btn.click(force=True)
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(random.uniform(1, 2))

                # 施設名のクリック
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)
                
                # 部屋名のクリック（ここが最大の難所）
                keywords = target['room'].split('|')
                found_room = False
                for kw in keywords:
                    room_link = page.locator(f"a:has-text('{kw}')").first
                    if await room_link.count() > 0:
                        # 画面が切り替わるまで最大3回、JSで強制クリック
                        for retry in range(3):
                            await room_link.dispatch_event("click")
                            await asyncio.sleep(5)
                            if await page.locator("table.cal_table").count() > 0:
                                found_room = True
                                break
                            print(f"    ...画面遷移リトライ中 ({retry+1}/3)")
                    if found_room: break
                
                if not found_room:
                    print(f"    ! 部屋が見つからないか、カレンダー画面へ進めませんでした。")
                    continue

                for _ in range(3):
                    await check_calendar_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click(force=True)
                        await asyncio.sleep(random.uniform(2, 4))
                    else:
                        break
            except Exception as e:
                print(f"    ! エラー発生: {e}")
                continue

        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件の空きを Kingdom へ報告しました。")
        else:
            print("本日のチェック終了。条件に合う空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き(△)を発見！"
    body = "以下の空き枠が見つかりました。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
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
