import os
import smtplib
from email.mime.text import MIMEText
import asyncio
import re
from playwright.async_api import async_playwright

# --- 設定エリア ---
# 通知を受け取りたいメールアドレス
RECIPIENT_EMAIL = "badmintonkingdom@icloud.com"
# 送信元（iCloudメール）
SENDER_EMAIL = "badmintonkingdom@icloud.com"

async def run():
    async with async_playwright() as p:
        # ブラウザの起動
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        found_vacancies = []

        # 施設リストの設定 
        # filter: True = 「土日祝は全日、平日は19-21時のみ」チェックする施設
        # filter: False = 全時間帯チェックする施設
        targets = [
            {"name": "鈴谷公民館", "room": "多目的ホール", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室", "filter": True},
            {"name": "浦和西体育館", "room": "競技場", "filter": True},
            {"name": "与野体育館", "room": "競技場", "filter": True},
            {"name": "大宮体育館", "room": "競技場", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場１／２", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ１／２", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            calendar_table = page.locator("table.cal_table")
            if await calendar_table.count() == 0: return

            # 現在表示されている月を取得
            month_label = page.locator("td.cal_month, .cal_month_area")
            month_text = await month_label.first.inner_text() if await month_label.count() > 0 else ""
            month_text = month_text.strip().replace("\n", "")

            # カレンダーの各セルをチェック
            cells = calendar_table.locator("td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                # 「空き」アイコンがあるか
                if await cell.locator("img[alt*='空き']").count() > 0:
                    day_text = await cell.locator(".cal_day").inner_text()
                    
                    # 土日祝日かどうか判定
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    # 条件に合致するか判定
                    if not filter_time or is_weekend:
                        # 全時間帯OK、または土日祝の場合
                        found_vacancies.append(f"【{facility_name}】{month_text}{day_text}に空きあり")
                    else:
                        # 平日の時間指定（19-21時）チェック
                        await cell.locator("a").first.click()
                        await asyncio.sleep(1)
                        # 19:00の枠に空きアイコンがあるか確認
                        slot_19 = page.locator("tr", has_text="19:00").locator("img[alt*='空き']")
                        if await slot_19.count() > 0:
                            found_vacancies.append(f"【{facility_name}】{month_text}{day_text} 19-21時に空きあり！")
                        
                        # カレンダーに戻る
                        await page.get_by_role("link", name="もどる").click()
                        await asyncio.sleep(1)

        # 全施設を巡回
        for target in targets:
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/")
                await page.get_by_role("link", name="施設の空き状況").click()
                await page.get_by_role("link", name="利用目的から").click()
                await page.get_by_role("link", name="屋内スポーツ").click()
                await page.get_by_role("link", name="バドミントン").click()

                # 施設名をクリック
                await page.get_by_role("link", name=re.compile(target['name'])).click()
                
                # 特定の部屋名があればクリック
                room_link = page.get_by_role("link", name=re.compile(target['room']))
                if await room_link.count() > 0:
                    await room_link.first.click()

                # 3ヶ月分をチェック
                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    await page.get_by_role("link", name="次の月").click()
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"{target['name']} の巡回中にエラー（スキップします）: {e}")

        # 空きが見つかった場合のみメール送信
        if found_vacancies:
            subject = "【Kingdom予約】★体育館に空きが出ました！★"
            body = "Kingdom運営用：以下の枠が予約可能です。早めにチェックしてください！\n\n"
            body += "\n".join(found_vacancies)
            body += "\n\n▼予約サイトはこちら\nhttps://saitama.rsv.ws-scs.jp/web/"
            
            send_email(subject, body)
            print("空きを発見！メールを送信しました。")
        else:
            print("条件に合う空きはありませんでした。")

        await context.close()
        await browser.close()

def send_email(subject, body):
    # GitHubのSecretsに登録したパスワードを使用
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password:
        print("エラー: App用パスワードが設定されていません。")
        return

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
