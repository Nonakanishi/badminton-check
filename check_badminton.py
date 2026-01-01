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
        # 人間に見せかけるための設定
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        page.set_default_timeout(45000) # 45秒に短縮（効率化）

        found_vacancies = []

        # 施設リスト（キーワードを最適化）
        targets = [
            {"name": "鈴谷公民館", "room": "多目的ホール", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室|競技場", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True}, # キーワードを絞る
            {"name": "浦和駒場体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            # カレンダーの出現を待つ
            try:
                await page.wait_for_selector("table.cal_table", timeout=15000)
            except:
                return # カレンダーがない場合は次へ

            month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
            month_text = month_text.strip().replace("\n", "")

            # 空きアイコンを一括検索
            cells = page.locator("td:has(img[alt*='空き'], img[alt*='一部'], img[alt*='予約可'])")
            count = await cells.count()
            
            for i in range(count):
                cell = cells.nth(i)
                day_text = await cell.locator(".cal_day").inner_text()
                alt_text = await cell.locator("img").first.get_attribute("alt")
                
                class_attr = await cell.get_attribute("class") or ""
                is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                if not filter_time or is_weekend:
                    found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                    print(f"  [発見] {month_text}{day_text}日: {alt_text}")

        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                # 1. サイトを開く
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                
                # 2. メニューを順番にクリック（人間に近い速度で）
                await page.get_by_role("link", name="施設の空き状況").click()
                await page.get_by_role("link", name="利用目的から").click()
                await page.get_by_role("link", name="屋内スポーツ").click()
                await page.get_by_role("link", name="バドミントン").click()

                # 3. 施設選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click()
                
                # 4. 部屋選択（ここが一番の修正ポイント：全スキャンを廃止）
                # リンクテキストにキーワードが含まれるものを直接指定
                room_locator = page.locator(f"a:has-text('{target['room'].split('|')[0]}')").first
                await room_locator.click()

                # 5. 3ヶ月分チェック
                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await asyncio.sleep(1) # 少し待機
                    else:
                        break

            except Exception as e:
                print(f"  ! {target['name']} でエラー: {e}")
                # エラー時の画面を保存（デバッグ用：GitHubのArtifactsで確認可能）
                await page.screenshot(path=f"error_{target['name']}.png")
                continue 

        # 通知処理
        if found_vacancies:
            send_notification(found_vacancies)
        else:
            print("本日のチェック終了：条件に合う空きはありませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空きを発見！"
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
        print(f"メール送信完了: {len(vacancies)} 件")
    except:
        print("メール送信失敗")

if __name__ == "__main__":
    asyncio.run(run())
