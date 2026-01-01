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
        # 人間に見せかけるための設定を強化
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []

        # 施設リスト：大宮は「アリーナ１」を狙い撃ち
        targets = [
            {"name": "鈴谷公民館", "room": "多目的", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            # カレンダーが出るまで最大30秒待機
            try:
                await page.wait_for_selector("table.cal_table", timeout=30000)
            except:
                return

            month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
            month_text = month_text.strip().replace("\n", "")

            # すべてのセルをチェック
            cells = page.locator("td")
            count = await cells.count()
            
            for i in range(count):
                cell = cells.nth(i)
                # 画像(img)が含まれるセルだけを見る
                img = cell.locator("img")
                if await img.count() > 0:
                    alt_text = await img.first.get_attribute("alt") or ""
                    # 「予約あり(×)」「休館」「受付期間外」以外はすべて「空き」として検知
                    if any(x in alt_text for x in ["空き", "一部", "予約可"]):
                        day_text = await cell.locator(".cal_day").inner_text()
                        
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
                
                # 2. メニュー移動（dispatch_eventでクリックミスを回避）
                for link_name in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    btn = page.get_by_role("link", name=link_name)
                    await btn.wait_for(state="attached")
                    await btn.dispatch_event("click")
                    await asyncio.sleep(1)

                # 3. 施設選択
                facility_btn = page.get_by_role("link", name=re.compile(target['name'])).first
                await facility_btn.dispatch_event("click")
                await asyncio.sleep(1)
                
                # 4. 部屋選択（「アリーナ１単位」などに対応）
                room_btn = page.locator(f"a:has-text('{target['room'].split('|')[0]}')").first
                await room_btn.wait_for(state="attached")
                await room_btn.dispatch_event("click") # 強制クリック
                
                # 5. カレンダーチェック
                for _ in range(3):
                    await page.wait_for_load_state("networkidle")
                    await check_current_page(target['name'], target['filter'])
                    
                    # 「翌月」移動
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.dispatch_event("click")
                        await asyncio.sleep(2)
                    else:
                        break

            except Exception as e:
                print(f"  ! {target['name']} でエラー: {e}")
                continue 

        # 通知
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件")
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
    except:
        pass

if __name__ == "__main__":
    asyncio.run(run())
