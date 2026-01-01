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
        # ブラウザの起動
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        found_vacancies = []

        # 施設リスト：room名を正規表現にし、アリーナ・競技場の両方に対応
        targets = [
            {"name": "鈴谷公民館", "room": "多目的ホール", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ|アリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            calendar_table = page.locator("table.cal_table")
            if await calendar_table.count() == 0: return

            # 月情報の取得
            month_label = page.locator("td.cal_month, .cal_month_area")
            month_text = await month_label.first.inner_text() if await month_label.count() > 0 else ""
            month_text = month_text.strip().replace("\n", "")

            # 各日付（セル）をチェック
            cells = calendar_table.locator("td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                # ★修正：空き(○)だけでなく、一部(△)のアイコンも検知対象にする
                vacancy_icons = cell.locator("img[alt*='空き'], img[alt*='一部'], img[alt*='予約可']")
                
                if await vacancy_icons.count() > 0:
                    day_text = await cell.locator(".cal_day").inner_text()
                    alt_text = await vacancy_icons.first.get_attribute("alt")
                    
                    # 土日祝判定
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    # 条件判定
                    if not filter_time or is_weekend:
                        found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                        print(f"  [発見] {month_text}{day_text}日: {alt_text}")
                    else:
                        # 平日夜間（19-21時）の個別チェック
                        try:
                            await cell.locator("a").first.click()
                            await asyncio.sleep(0.8)
                            # 19:00枠のチェック
                            slot_19 = page.locator("tr", has_text="19:00").locator("img[alt*='空き'], img[alt*='一部'], img[alt*='予約可']")
                            if await slot_19.count() > 0:
                                found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日 19-21時")
                                print(f"  [発見] {month_text}{day_text}日 夜間枠")
                            
                            await page.get_by_role("link", name="もどる").click()
                            await asyncio.sleep(0.8)
                        except:
                            continue

        # 巡回メイン処理
        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/")
                await page.get_by_role("link", name="施設の空き状況").click()
                await page.get_by_role("link", name="利用目的から").click()
                await page.get_by_role("link", name="屋内スポーツ").click()
                await page.get_by_role("link", name="バドミントン").click()

                # 施設クリック
                await page.get_by_role("link", name=re.compile(target['name'])).click()
                
                # 部屋クリック（正規表現で柔軟に）
                room_link = page.get_by_role("link", name=re.compile(target['room']))
                if await room_link.count() > 0:
                    await room_link.first.click()
                else:
                    print(f"  ! 部屋が見つかりません: {target['room']}")
                    continue

                # 3ヶ月分をループ
                for month_idx in range(3):
                    await check_current_page(target['name'], target['filter'])
                    # 「翌月」または「次の月」ボタンを探してクリック
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await asyncio.sleep(0.8)
                    else:
                        break
            except Exception as e:
                print(f"  ! {target['name']} でエラー発生: {e}")

        # メール送信
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件")
        else:
            print("空きはありませんでした。")

        await context.close()
        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password:
        print("エラー: アプリ用パスワードが設定されていません。")
        return

    subject = "【Kingdom予約】体育館に空き（一部空き含む）を発見！"
    body = "以下の枠が予約可能です。早めに予約サイトを確認してください。\n\n"
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
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    asyncio.run(run())
