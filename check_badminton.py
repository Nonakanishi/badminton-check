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
        # ★PC版のブラウザとして起動
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1000}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []
        
        # 施設リスト：スクリーンショットの正確な表記に合わせました
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ１／４|体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１単位|アリーナ１", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False}
        ]

        async def check_calendar(facility_name, filter_time):
            # カレンダーの表（cal_table）が出るまで粘り強く待つ
            try:
                await page.wait_for_selector("table.cal_table", timeout=30000)
                await asyncio.sleep(2) # アイコンの描画待ち
            except:
                print(f"  ! {facility_name}: カレンダーの表が見つかりません。")
                return

            month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
            month_text = month_text.strip().replace("\n", "")

            # すべてのセルをチェック
            cells = page.locator("table.cal_table td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                # ★三角マーク(一部空き)と丸マーク(空き)の両方をチェック
                img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                if await img.count() > 0:
                    alt = await img.first.get_attribute("alt")
                    day = await cell.locator(".cal_day").inner_text()
                    
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    if not filter_time or is_weekend:
                        found_vacancies.append(f"【{facility_name}】{month_text}{day}日({alt})")
                        print(f"  [発見] {day}日: {alt}")

        # 巡回
        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                
                # PC版のメニュー遷移
                for step in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    await page.get_by_role("link", name=step).click(force=True)
                    await asyncio.sleep(1)

                # 施設選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(1)
                
                # 部屋選択（ここを正確に）
                room_kw = target['room'].split('|')[0]
                await page.locator(f"a:has-text('{room_kw}')").first.click(force=True)
                
                # 今月〜3ヶ月分をチェック
                for _ in range(3):
                    await check_calendar(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click(force=True)
                        await asyncio.sleep(2)
                    else:
                        break
            except Exception as e:
                print(f"  ! {target['name']} でエラー: {e}")
                # エラー時の画面を保存
                await page.screenshot(path=f"error_{target['name']}.png")
                continue

        # 最終結果の通知
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件の空きを発見！")
        else:
            print("空きは見つかりませんでした。現在の画面をデバッグ用に保存します。")
            await page.screenshot(path="final_view.png")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き（△）を発見しました！"
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
