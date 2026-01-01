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
        # ブラウザの起動（タイムアウトを長めに設定）
        browser = await p.chromium.launch(headless=True)
        # 混雑対策：タイムアウトを60秒(60000ms)に設定
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        page = await context.new_page()
        page.set_default_timeout(60000) 
        
        found_vacancies = []

        # 施設リスト：スクリーンショットの「単位」や「１」などの表記揺れに完全対応
        targets = [
            {"name": "鈴谷公民館", "room": "多目的ホール", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室|競技場", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１|アリーナ２|アリーナ　１", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ|メインアリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            calendar_table = page.locator("table.cal_table")
            if await calendar_table.count() == 0: return

            month_label = page.locator("td.cal_month, .cal_month_area")
            month_text = await month_label.first.inner_text() if await month_label.count() > 0 else ""
            month_text = month_text.strip().replace("\n", "")

            cells = calendar_table.locator("td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                # ★重要：○(空き)だけでなく△(一部空き)も検知
                vacancy_icons = cell.locator("img[alt*='空き'], img[alt*='一部'], img[alt*='予約可']")
                
                if await vacancy_icons.count() > 0:
                    day_text = await cell.locator(".cal_day").inner_text()
                    alt_text = await vacancy_icons.first.get_attribute("alt")
                    
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    if not filter_time or is_weekend:
                        found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                        print(f"  [発見] {month_text}{day_text}日: {alt_text}")
                    else:
                        # 平日夜間（19-21時）の個別チェック
                        try:
                            await cell.locator("a").first.click()
                            await asyncio.sleep(1.5) # 混雑時は長めに待機
                            slot_19 = page.locator("tr", has_text="19:00").locator("img[alt*='空き'], img[alt*='一部']")
                            if await slot_19.count() > 0:
                                found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日 19-21時")
                                print(f"  [発見] {month_text}{day_text}日 夜間枠")
                            
                            await page.get_by_role("link", name="もどる").click()
                            await asyncio.sleep(1)
                        except:
                            continue

        # 巡回メイン
        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                # 混雑対策：リトライ機能
                for attempt in range(3):
                    try:
                        await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                        break
                    except:
                        if attempt == 2: raise
                        await asyncio.sleep(5)

                await page.get_by_role("link", name="施設の空き状況").click()
                await page.get_by_role("link", name="利用目的から").click()
                await page.get_by_role("link", name="屋内スポーツ").click()
                await page.get_by_role("link", name="バドミントン").click()

                # 施設クリック
                await page.get_by_role("link", name=re.compile(target['name'])).click()
                
                # 部屋クリック（「アリーナ１単位」など部分一致でヒットさせる）
                room_link = page.get_by_role("link", name=re.compile(target['room']))
                if await room_link.count() > 0:
                    await room_link.first.click()
                else:
                    print(f"  ! 部屋名 '{target['room']}' が見つかりません。スキップします。")
                    continue

                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await asyncio.sleep(1.5)
                    else:
                        break
            except Exception as e:
                print(f"  ! {target['name']} でエラー（混雑による中断の可能性）: {e}")
                continue # エラーが起きても次の施設へ進む

        # メール送信
        if found_vacancies:
            send_notification(found_vacancies)
        else:
            print("空きはありませんでした。")

        await context.close()
        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password:
        print("エラー: ICLOUD_APP_PASSWORD が未設定です。")
        return

    subject = "【Kingdom速報】体育館の空き枠を発見しました！"
    body = "以下の空きが見つかりました。早めに予約サイトを確認してください。\n\n"
    body += "\n".join(vacancies)
    body += "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    try:
        with smtplib.SMTP("smtp.mail.me.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
        print(f"メール送信完了: {len(vacancies)} 件の通知を送りました。")
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    asyncio.run(run())
