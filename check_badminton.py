import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import asyncio
import re
import random
from playwright.async_api import async_playwright

# --- 設定エリア ---
RECIPIENT_EMAIL = "badmintonkingdom@icloud.com"
SENDER_EMAIL = "badmintonkingdom@icloud.com"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []
        error_images = []

        # 巡回対象：三橋と大宮を最優先
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "鈴谷公民館", "room": "多目的", "filter": False}
        ]

        async def check_calendar_page(facility_name, filter_time):
            try:
                # カレンダーの表が出るのを待つ
                await page.wait_for_selector("table.cal_table", timeout=30000)
                
                month_text = await page.locator("td.cal_month, .cal_month_area").first.inner_text()
                month_text = month_text.strip().replace("\n", "")

                cells = page.locator("table.cal_table td")
                for i in range(await cells.count()):
                    cell = cells.nth(i)
                    img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                    if await img.count() > 0:
                        alt = await img.first.get_attribute("alt")
                        day = await cell.locator(".cal_day").inner_text()
                        class_attr = await cell.get_attribute("class") or ""
                        is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                        if not filter_time or is_weekend:
                            found_vacancies.append(f"【{facility_name}】{month_text}{day}日({alt})")
                            print(f"  [発見] {facility_name} {day}日: {alt}")
            except:
                # 失敗したらその画面を保存
                path = f"error_{facility_name}.png"
                await page.screenshot(path=path)
                error_images.append(path)
                print(f"    ! {facility_name}: カレンダーの読み取りに失敗しました（画像を保存）")

        for target in targets:
            print(f">>> {target['name']} を開始...")
            try:
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                
                # 手順：施設から予約（こちらの方が混雑に強い傾向があります）
                steps = ["施設の空き状況", "施設から探す"]
                for step in steps:
                    await page.get_by_role("link", name=step).click(force=True)
                    await asyncio.sleep(1)

                # 施設名を検索してクリック
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(2)
                
                # 部屋選択
                keywords = target['room'].split('|')
                room_link = None
                for kw in keywords:
                    link = page.locator(f"a:has-text('{kw}')").first
                    if await link.count() > 0:
                        room_link = link
                        break
                
                if room_link:
                    await room_link.click(force=True)
                    await check_calendar_page(target['name'], target['filter'])
                else:
                    # 部屋が見つからない場合も撮影
                    path = f"missing_{target['name']}.png"
                    await page.screenshot(path=path)
                    error_images.append(path)
                    print(f"    ! {target['name']}: 部屋が見つかりませんでした。")

            except Exception as e:
                print(f"    ! {target['name']} 中断: {e}")
                continue

        # 通知
        if found_vacancies or error_images:
            send_notification(found_vacancies, error_images)

        await browser.close()

def send_notification(vacancies, image_paths):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return

    msg = MIMEMultipart()
    msg["Subject"] = "【Kingdom】空き状況チェック報告"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    body = "本日の空き状況チェック結果です。\n\n"
    if vacancies:
        body += "■発見した空き枠:\n" + "\n".join(vacancies) + "\n\n"
    else:
        body += "条件に合う空き枠は見つかりませんでした。\n\n"

    if image_paths:
        body += "※一部の施設でカレンダーを開けませんでした。エラー画面を添付します。\n"
    
    msg.attach(MIMEText(body, "plain"))

    for path in image_paths:
        if os.path.exists(path):
            with open(path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename=path)
                msg.attach(img)

    try:
        with smtplib.SMTP("smtp.mail.me.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
        print("メールを送信しました。")
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    asyncio.run(run())
