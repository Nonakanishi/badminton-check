import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import asyncio
import re
from playwright.async_api import async_playwright

# --- 設定エリア ---
RECIPIENT_EMAIL = "badmintonkingdom@icloud.com"
SENDER_EMAIL = "badmintonkingdom@icloud.com"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 偽装をさらに強化
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200},
            accept_downloads=True
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []
        error_images = []

        # 巡回対象
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True}
        ]

        async def capture(name):
            path = f"debug_{name}.png"
            await page.screenshot(path=path)
            error_images.append(path)

        for target in targets:
            print(f">>> {target['name']} をチェック中...")
            try:
                # 1. サイトを開く
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                await asyncio.sleep(2)

                # 2. 「施設の空き状況」をクリック（文字ではなくリンクの構造で探す）
                # サイトの1番目のメインメニューであることが多いため、強引にクリック
                menu_links = page.locator("a")
                
                # 「施設の空き状況」を探す
                await page.locator("a:has-text('施設の空き状況')").first.click(force=True)
                await asyncio.sleep(2)

                # 3. 「施設から探す」をクリック
                # ここで躓いているため、複数の指定方法を試す
                try:
                    await page.locator("a:has-text('施設から探す')").first.click(timeout=10000)
                except:
                    # テキストで見つからない場合、現在の画面を撮影してスキップ
                    print(f"  ! メニューが見つかりません。現在の画面を撮影します。")
                    await capture(target['name'])
                    continue

                # 4. 施設名を選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(2)
                
                # 5. 部屋選択
                room_link = page.locator(f"a:has-text('{target['room'].split('|')[0]}')").first
                await room_link.click(force=True)
                
                # 6. カレンダー読み取り
                await page.wait_for_selector("table.cal_table", timeout=20000)
                cells = page.locator("table.cal_table td")
                for i in range(await cells.count()):
                    cell = cells.nth(i)
                    img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                    if await img.count() > 0:
                        alt = await img.first.get_attribute("alt")
                        day = await cell.locator(".cal_day").inner_text()
                        found_vacancies.append(f"【{target['name']}】{day}日({alt})")

            except Exception as e:
                print(f"  ! {target['name']} でエラー: {e}")
                await capture(target['name'])

        # 通知
        if found_vacancies or error_images:
            send_notification(found_vacancies, error_images)

        await browser.close()

def send_notification(vacancies, image_paths):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    msg = MIMEMultipart()
    msg["Subject"] = "【Kingdom】自動巡回・画像報告"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    body = "チェック結果報告です。\n\n"
    if vacancies:
        body += "■空き発見:\n" + "\n".join(vacancies) + "\n\n"
    if image_paths:
        body += "※一部の画面でボタンが見つかりませんでした。添付画像を確認してください。\n"
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
    except: pass

if __name__ == "__main__":
    asyncio.run(run())

