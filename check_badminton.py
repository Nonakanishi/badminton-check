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
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []
        debug_images = []

        # 巡回対象：三橋の部屋名をスクリーンショット通りに修正
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True}, # 「Ａ」で部分一致
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "与野体育館", "room": "競技場|アリーナ", "filter": True}
        ]

        async def save_debug(name):
            path = f"debug_{name}.png"
            await page.screenshot(path=path)
            debug_images.append(path)

        for target in targets:
            print(f">>> {target['name']} をチェック中...")
            try:
                # 1. トップページを開く
                await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                
                # 2. 「施設の空き状況」をクリック（画像や文字など複数の方法で試行）
                # さいたま市のシステムは画像ボタンのため、alt属性やテキストで柔軟に探す
                vacancy_btn = page.locator("a:has(img[alt*='空き状況']), a:has-text('施設の空き状況')").first
                await vacancy_btn.click(force=True)
                await asyncio.sleep(2)

                # 3. 「利用目的から探す」をクリック
                purpose_btn = page.locator("a:has(img[alt*='利用目的']), a:has-text('利用目的')").first
                await purpose_btn.click(force=True)
                await asyncio.sleep(2)

                # 4. 「屋内スポーツ」->「バドミントン」
                await page.locator("a:has-text('屋内スポーツ')").first.click(force=True)
                await page.locator("a:has-text('バドミントン')").first.click(force=True)

                # 5. 施設名を選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(2)
                
                # 6. 部屋選択（「体育室Ａ」を含むリンクをクリック）
                room_link = page.locator(f"a:has-text('{target['room']}')").first
                await room_link.click(force=True)
                
                # 7. 3ヶ月分をくまなくチェック
                for _ in range(3):
                    await page.wait_for_selector("table.cal_table", timeout=20000)
                    cells = page.locator("table.cal_table td")
                    for i in range(await cells.count()):
                        cell = cells.nth(i)
                        # ★ここが重要：△(一部空き)の緑色アイコンを確実に検知
                        img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                        if await img.count() > 0:
                            alt = await img.first.get_attribute("alt")
                            day = await cell.locator(".cal_day").inner_text()
                            found_vacancies.append(f"【{target['name']}】{day}日({alt})")
                            print(f"  [発見] {day}日: {alt}")

                    # 翌月へ
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click(force=True)
                        await asyncio.sleep(2)
                    else:
                        break

            except Exception as e:
                print(f"  ! {target['name']} でエラー: {e}")
                await save_debug(target['name'])

        # メール通知
        if found_vacancies or debug_images:
            send_notification(found_vacancies, debug_images)

        await browser.close()

def send_notification(vacancies, image_paths):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    msg = MIMEMultipart()
    msg["Subject"] = "【Kingdom速報】空き状況・精査報告"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    body = "本日のチェック結果です。\n\n"
    if vacancies:
        body += "■以下の空き（△含む）が見つかりました：\n" + "\n".join(vacancies) + "\n\n"
    else:
        body += "条件に合う空きは見つかりませんでした。\n\n"
    if image_paths:
        body += "※一部の操作でエラーが発生したため、画面を添付します。\n"
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
