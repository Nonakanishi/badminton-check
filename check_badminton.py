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
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(90000) # 混雑対応で90秒に設定

        found_vacancies = []
        
        # ターゲット施設
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False}
        ]

        async def check_calendar(facility_name, filter_time):
            try:
                await page.wait_for_selector("table.cal_table", timeout=30000)
                month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
                month_text = month_text.strip().replace("\n", "")

                cells = page.locator("table.cal_table td")
                for i in range(await cells.count()):
                    cell = cells.nth(i)
                    # ★△（一部空き）マークを確実に検知
                    img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                    if await img.count() > 0:
                        alt = await img.first.get_attribute("alt")
                        day = await cell.locator(".cal_day").inner_text()
                        class_attr = await cell.get_attribute("class") or ""
                        is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                        if not filter_time or is_weekend:
                            found_vacancies.append(f"【{facility_name}】{month_text}{day}日({alt})")
                            print(f"  [発見] {facility_name} {day}日: {alt}")
            except: pass

        try:
            print(">>> 予約サイトへ接続中...")
            await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
            
            # --- 手順を最短化：文字が見えなくても「アイコンの位置」や「説明文」で進む ---
            print(">>> バドミントン一覧画面へ移動中...")
            # 1. 空き状況
            await page.locator("a:has(img[alt*='空き状況'])").first.click()
            # 2. 利用目的
            await page.locator("a:has(img[alt*='目的'])").first.click()
            # 3. 画面上の4番目か5番目にある「屋内スポーツ」に相当するアイコンを強引に探してクリック
            await page.locator("a:has(img[src*='purpose_05']), a:has(img[alt*='スポーツ'])").first.click()
            # 4. バドミントン
            await page.locator("a:has(img[alt*='バドミントン']), a:has-text('バドミントン')").first.click()
            
            # --- 一度一覧に入ったら、ここから各施設を巡回 ---
            for target in targets:
                print(f">>> {target['name']} を確認中...")
                try:
                    # 施設リンクをクリック
                    facility_link = page.locator(f"a:has-text('{target['name']}')").first
                    if await facility_link.count() == 0:
                        # 文字が見えない場合のために、リンクを全部取得して検索
                        await page.evaluate(f"Array.from(document.querySelectorAll('a')).find(a => a.innerText.includes('{target['name']}')).click()")
                    else:
                        await facility_link.click()
                    
                    # 部屋選択
                    room_kw = target['room'].split('|')[0]
                    await page.locator(f"a:has-text('{room_kw}')").first.click()

                    # 3ヶ月分チェック
                    for _ in range(3):
                        await check_calendar(target['name'], target['filter'])
                        next_btn = page.locator("a:has(img[alt*='翌月']), a:has-text('翌月')").first
                        if await next_btn.count() > 0:
                            await next_btn.click()
                            await asyncio.sleep(1)
                        else: break
                    
                    # 「施設一覧に戻る」操作
                    await page.get_by_role("link", name="もどる").click()
                    await page.wait_for_load_state("networkidle")
                except:
                    # 失敗したら一度バドミントン一覧に戻る
                    await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                    # 再度ナビゲーション（ここは簡略化のため再実行）
                    continue

        except Exception as e:
            print(f"!!! 重大なエラー: {e}")

        # 結果送信
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件の空きを発見！")
        else:
            print("本日のチェック終了。空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き(△)を発見しました！"
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
