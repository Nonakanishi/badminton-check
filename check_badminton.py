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
        browser = await p.chromium.launch(headless=True)
        # 画面サイズを大きくして、すべてのリンクを確実に表示させる
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={'width': 1280, 'height': 2000}
        )
        page = await context.new_page()
        page.set_default_timeout(90000)

        found_vacancies = []

        # ターゲット：スクリーンショットの正確な名称に合わせました
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ１／４", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１単位", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ", "filter": True},
            {"name": "与野体育館", "room": "アリーナ", "filter": True}
        ]

        async def check_calendar_marks(facility_name, room_name, filter_time):
            try:
                # カレンダーの読み込みを待機
                await page.wait_for_selector("table.cal_table", timeout=30000)
                month_label = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
                month_text = month_label.strip().replace("\n", "")

                cells = page.locator("table.cal_table td")
                for i in range(await cells.count()):
                    cell = cells.nth(i)
                    # ★画像による判定を強化（mark_02.gif = △, mark_01.gif = ○）
                    # alt属性が消えていても、画像ファイル名で確実に検知します
                    mark = cell.locator("img[src*='mark_01'], img[src*='mark_02'], img[alt*='空き'], img[alt*='一部']")
                    
                    if await mark.count() > 0:
                        alt = await mark.first.get_attribute("alt") or "空きあり"
                        day = await cell.locator(".cal_day").inner_text()
                        class_attr = await cell.get_attribute("class") or ""
                        
                        # 日曜・祝日の判定をさらに強化
                        is_weekend = any(x in class_attr.lower() for x in ["sun", "sat", "holiday", "cal_7"])
                        
                        if not filter_time or is_weekend:
                            found_vacancies.append(f"【{facility_name}】{room_name} {month_text}{day}日({alt})")
                            print(f"    [発見!] {day}日: {alt}")
            except: pass

        try:
            print(">>> 予約サイトへ接続中...")
            await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
            
            # メニュー突破（画像URLを直接指定して「文字消え」を回避）
            await page.locator("a:has(img[src*='top_menu_01'])").click(force=True) # 施設の空き状況
            await asyncio.sleep(1)
            await page.locator("a:has(img[src*='srch_02'])").click(force=True) # 利用目的から
            await asyncio.sleep(1)
            await page.locator("a:has(img[src*='purpose_05'])").click(force=True) # 屋内スポーツ
            await asyncio.sleep(1)
            await page.locator("a:has(img[src*='ppsd_18'])").click(force=True) # バドミントン
            
            for target in targets:
                print(f"  - {target['name']} を精査中...")
                try:
                    # 施設名を正規表現で柔軟に探してクリック
                    await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                    await asyncio.sleep(1)

                    # ★部屋名をピンポイント指定
                    room_link = page.locator(f"a:has-text('{target['room']}')").first
                    if await room_link.count() == 0:
                        # 文字が消えている場合、部分一致で再試行
                        room_link = page.locator(f"a:has-text('{target['room'][:4]}')").first
                    
                    await room_link.click(force=True)
                    
                    # 3ヶ月分をくまなくチェック
                    for _ in range(3):
                        await check_calendar_marks(target['name'], target['room'], target['filter'])
                        next_btn = page.locator("a:has(img[src*='next_month']), a:has-text('翌月')").first
                        if await next_btn.count() > 0:
                            await next_btn.click(force=True)
                            await asyncio.sleep(1)
                        else: break
                    
                    # 戻って次の施設へ
                    await page.get_by_role("link", name="もどる").first.click(force=True)
                    await asyncio.sleep(1)
                except:
                    await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                    continue

        except Exception as e:
            print(f"!!! エラー: {e}")

        # 結果送信
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件を検知！")
        else:
            print("条件に合う空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom】三橋・大宮の△マークを検知！"
    body = "ご要望の枠（△含む）が見つかりました。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
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
