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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1600}
        )
        page = await context.new_page()
        # タイムアウトを2分(120秒)に設定
        page.set_default_timeout(120000)

        found_vacancies = []

        # 施設リスト：キーワードをより限定的に
        targets = [
            {"name": "鈴谷公民館", "room": "多目的", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True}, # Ａ１／４にヒット
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            # カレンダーが出るまで最大40秒、粘り強く待つ
            try:
                # tableが出るだけでなく、ページ内に「空き状況」の文字が出るまで待機
                await page.wait_for_selector("table.cal_table", timeout=40000, state="visible")
                await asyncio.sleep(2) # 描画完了まで念押しで待機
            except:
                print(f"    ! 画面の読み込みが間に合いませんでした ({facility_name})")
                return

            month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
            month_text = month_text.strip().replace("\n", "")

            # 画像が含まれるセルをすべて取得
            cells = page.locator("table.cal_table td")
            count = await cells.count()
            
            for i in range(count):
                cell = cells.nth(i)
                img = cell.locator("img")
                if await img.count() > 0:
                    alt_text = await img.first.get_attribute("alt") or ""
                    
                    # ★検知条件：△や○が含まれていれば全て拾う
                    if any(x in alt_text for x in ["一部", "空き", "予約可", "△", "○"]):
                        day_text = await cell.locator(".cal_day").inner_text()
                        class_attr = await cell.get_attribute("class") or ""
                        is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                        if not filter_time or is_weekend:
                            # 週末、または全日チェック施設の場合
                            found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                            print(f"  [★発見] {month_text}{day_text}日: {alt_text}")
                        else:
                            # 平日の場合は19時以降をチェック（ここも見落とし対策で強化）
                            try:
                                await cell.locator("a").first.click(force=True)
                                await page.wait_for_selector("tr", has_text="19:00", timeout=10000)
                                slot_19 = page.locator("tr", has_text="19:00").locator("img[alt*='空き'], img[alt*='一部']")
                                if await slot_19.count() > 0:
                                    found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日 19-21時")
                                    print(f"  [★発見] {month_text}{day_text}日: 夜間枠")
                                
                                await page.get_by_role("link", name="もどる").click(force=True)
                                await asyncio.sleep(1)
                            except:
                                continue

        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                # サイトを開く
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                
                # 手順を飛ばさず、一歩ずつ確実にクリック
                for link_name in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    await page.get_by_role("link", name=link_name).click(force=True)
                    await asyncio.sleep(1.5)

                # 施設選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(1.5)
                
                # 部屋選択（ここがカレンダーへの入り口）
                room_kw = target['room'].split('|')[0]
                room_link = page.locator(f"a:has-text('{room_kw}')").first
                await room_link.click(force=True)
                
                # 3ヶ月分をしっかりチェック
                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click(force=True)
                        await asyncio.sleep(3) # 月の切り替えは時間がかかるので長めに
                    else:
                        break

            except Exception as e:
                print(f"  ! {target['name']} でエラー: {e}")
                continue 

        # 結果をメール
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"完了: {len(found_vacancies)} 件の通知を送りました")
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
