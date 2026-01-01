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
        # ブラウザを人間に見せかけるための高度な設定
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200},
            locale="ja-JP"
        )
        page = await context.new_page()
        # タイムアウトを極限の3分(180秒)に設定
        page.set_default_timeout(180000)

        found_vacancies = []

        # ターゲット：三橋は「体育室Ａ」を優先
        targets = [
            {"name": "鈴谷公民館", "room": "多目的", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            # カレンダーが「完全に」表示されるまでしつこく待つ
            try:
                # サーバーが重いので、最大60秒間、カレンダーが出るまで待機
                await page.wait_for_selector("table.cal_table", timeout=60000, state="visible")
                await asyncio.sleep(2) 
            except:
                print(f"    ! サーバーの応答がありません ({facility_name})")
                return

            month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
            month_text = month_text.strip().replace("\n", "")

            # すべてのセルをなめる
            cells = page.locator("table.cal_table td")
            count = await cells.count()
            
            for i in range(count):
                cell = cells.nth(i)
                img = cell.locator("img")
                if await img.count() > 0:
                    alt_text = await img.first.get_attribute("alt") or ""
                    # ★検知条件：一部（△）や空き（○）があれば即座に拾う
                    if any(x in alt_text for x in ["一部", "空き", "予約可", "△", "○"]):
                        day_text = await cell.locator(".cal_day").inner_text()
                        class_attr = await cell.get_attribute("class") or ""
                        is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                        if not filter_time or is_weekend:
                            found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                            print(f"  [発見!] {month_text}{day_text}日: {alt_text}")

        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                # サイトを開く（リトライ付き）
                for _ in range(3):
                    try:
                        await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded", timeout=60000)
                        break
                    except:
                        await asyncio.sleep(5)

                # メニューを順番にクリック
                for step in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    btn = page.get_by_role("link", name=step)
                    await btn.click(force=True)
                    await asyncio.sleep(random.uniform(1.0, 2.0))

                # 施設選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(2)
                
                # 部屋選択（ここがカレンダーへの門番）
                room_kw = target['room'].split('|')[0]
                room_btn = page.locator(f"a:has-text('{room_kw}')").first
                # クリックが成功するまで最大3回試す
                for _ in range(3):
                    await room_btn.click(force=True)
                    await asyncio.sleep(3)
                    if await page.locator("table.cal_table").count() > 0:
                        break

                # 3ヶ月分チェック
                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click(force=True)
                        await asyncio.sleep(3)
                    else:
                        break
            except Exception as e:
                print(f"  ! {target['name']} 中断: サーバー接続エラー")
                continue 

        # 通知
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件見つかりました")
        else:
            print("条件に合う空きは見つかりませんでした（サーバーが情報を返しませんでした）")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き（△）を発見！"
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
    except:
        pass

if __name__ == "__main__":
    asyncio.run(run())
