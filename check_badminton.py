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
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={'width': 1280, 'height': 1500}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []

        # ターゲット：三橋は「Ａ」がつく全ての部屋をチェック対象に
        targets = [
            {"name": "三橋総合公園", "room_kw": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room_kw": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room_kw": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room_kw": "アリーナ|競技場", "filter": True}
        ]

        async def check_current_calendar(facility_name, room_name, filter_time):
            try:
                await page.wait_for_selector("table.cal_table", timeout=20000)
                month_label = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
                month_text = month_label.strip().replace("\n", "")

                cells = page.locator("table.cal_table td")
                for i in range(await cells.count()):
                    cell = cells.nth(i)
                    # ★検知感度アップ：imgタグがあれば、altに関わらず中身を確認
                    img = cell.locator("img")
                    if await img.count() > 0:
                        alt = await img.first.get_attribute("alt") or ""
                        # △(一部空き)や○(空き)を逃さずキャッチ
                        if any(x in alt for x in ["一部", "空き", "予約可"]):
                            day = await cell.locator(".cal_day").inner_text()
                            class_attr = await cell.get_attribute("class") or ""
                            
                            # 曜日の判定を強化（sun, sat, holiday, または日曜日の色設定）
                            is_weekend = any(x in class_attr.lower() for x in ["sun", "sat", "holiday", "cal_7"])
                            
                            if not filter_time or is_weekend:
                                found_vacancies.append(f"【{facility_name}】{room_name} {month_text}{day}日({alt})")
                                print(f"    [発見!] {day}日: {alt} ({room_name})")
            except: pass

        try:
            print(">>> 予約サイトへ接続中...")
            await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
            
            # メニュー突破
            await page.locator(".menu_btn_area a, #disp a").first.click(force=True)
            await asyncio.sleep(1)
            await page.locator(".menu_btn_area a, #disp a").nth(1).click(force=True)
            await asyncio.sleep(1)
            await page.locator("a:has(img[src*='05']), a:has(img[alt*='スポーツ'])").first.click(force=True)
            await asyncio.sleep(1)
            await page.locator("a:has(img[alt*='バドミントン'])").first.click(force=True)
            
            print(">>> 施設巡回を開始します。")

            for target in targets:
                print(f"  - {target['name']} を調査中...")
                try:
                    await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                    await asyncio.sleep(1)

                    # ★三橋対策：キーワード（体育室Ａなど）に一致する「全ての」部屋を巡回
                    room_links = page.locator(f"a:has-text('{target['room_kw']}')")
                    room_count = await room_links.count()
                    
                    for r in range(room_count):
                        # リンクが消えないように毎回取得し直す
                        current_links = page.locator(f"a:has-text('{target['room_kw']}')")
                        room_name = await current_links.nth(r).inner_text()
                        print(f"    ...部屋を確認中: {room_name}")
                        
                        await current_links.nth(r).click(force=True)
                        
                        # 3ヶ月分チェック
                        for _ in range(3):
                            await check_current_calendar(target['name'], room_name, target['filter'])
                            next_btn = page.locator("a:has-text('翌月'), a:has(img[alt*='翌月'])").first
                            if await next_btn.count() > 0:
                                await next_btn.click(force=True)
                                await asyncio.sleep(1)
                            else: break
                        
                        # 部屋選択画面に戻る
                        await page.get_by_role("link", name="もどる").first.click(force=True)
                        await asyncio.sleep(1)

                    # 施設一覧に戻る
                    await page.get_by_role("link", name="もどる").first.click(force=True)
                except:
                    await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                    continue

        except Exception as e:
            print(f"!!! エラー発生: {e}")

        # 結果を送信
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件の空き（△含む）を発見しました！")
        else:
            print("条件に合う空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom最速】三橋の△マークを検知しました！"
    body = "以下の空き枠が見つかりました。早めに確認してください。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
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
