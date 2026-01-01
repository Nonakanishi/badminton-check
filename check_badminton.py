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
        # ブラウザの起動設定
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []

        # ターゲット施設
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False}
        ]

        async def navigate_to_badminton():
            await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
            # 1. 「施設の空き状況」アイコンをクリック (alt属性を利用)
            await page.locator("a:has(img[alt*='空き状況'])").first.click()
            await page.wait_for_load_state("networkidle")
            # 2. 「利用目的から探す」アイコンをクリック
            await page.locator("a:has(img[alt*='利用目的'])").first.click()
            await page.wait_for_load_state("networkidle")
            # 3. 「屋内スポーツ」アイコンをクリック
            await page.locator("a:has(img[alt*='屋内スポーツ'])").first.click()
            await page.wait_for_load_state("networkidle")
            # 4. 「バドミントン」アイコンをクリック
            await page.locator("a:has(img[alt*='バドミントン'])").first.click()
            await page.wait_for_load_state("networkidle")

        async def check_calendar(facility_name, filter_time):
            try:
                # カレンダーの出現を待つ
                await page.wait_for_selector("table.cal_table", timeout=20000)
                
                # 月情報の取得
                month_label = page.locator("td.cal_month, .cal_month_area").first
                month_text = await month_label.inner_text()
                month_text = month_text.strip().replace("\n", "")

                # セルをチェック
                cells = page.locator("table.cal_table td")
                for i in range(await cells.count()):
                    cell = cells.nth(i)
                    # ★三角(△)アイコンを狙い撃ち (alt属性に「一部」が含まれる画像を検索)
                    vacancy_img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                    
                    if await vacancy_img.count() > 0:
                        alt_text = await vacancy_img.first.get_attribute("alt")
                        day_text = await cell.locator(".cal_day").inner_text()
                        
                        class_attr = await cell.get_attribute("class") or ""
                        is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                        if not filter_time or is_weekend:
                            found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                            print(f"  [発見] {facility_name} {month_text}{day_text}日: {alt_text}")
            except Exception as e:
                print(f"    ! {facility_name} カレンダー確認不可: {e}")

        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                await navigate_to_badminton()
                
                # ★文字が消える問題への対策：JavaScriptで内部テキストを強引に読み取ってクリック
                await page.evaluate(f"""
                    (name) => {{
                        const links = Array.from(document.querySelectorAll('a'));
                        const target = links.find(a => a.textContent.includes(name));
                        if (target) target.click();
                        else throw new Error('Facility link not found: ' + name);
                    }}
                """, target['name'])
                await page.wait_for_load_state("networkidle")

                # 部屋選択も同様
                room_kw = target['room'].split('|')[0]
                await page.evaluate(f"""
                    (kw) => {{
                        const links = Array.from(document.querySelectorAll('a'));
                        const target = links.find(a => a.textContent.includes(kw));
                        if (target) target.click();
                        else throw new Error('Room link not found: ' + kw);
                    }}
                """, room_kw)
                
                # 3ヶ月分チェック
                for _ in range(3):
                    await check_calendar(target['name'], target['filter'])
                    next_btn = page.locator("a:has(img[alt*='翌月']), a:has(img[alt*='次の月'])").first
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(1)
                    else:
                        break
            except Exception as e:
                print(f"  ! {target['name']} 巡回スキップ: {e}")
                continue

        # 結果をメール送信
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件")
        else:
            print("空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き枠(△)を発見！"
    body = "以下の空きが見つかりました。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
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
