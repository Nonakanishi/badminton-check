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
        # ブラウザの起動（人間に見せかける偽装を最大化）
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            viewport={'width': 390, 'height': 844}, # スマホ版としてアクセスして負荷を軽減
            locale="ja-JP"
        )
        page = await context.new_page()
        page.set_default_timeout(90000)

        found_vacancies = []
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False}
        ]

        async def check_current_page(facility_name):
            try:
                # カレンダー表示を待機
                await page.wait_for_selector("table.cal_table", timeout=30000)
                cells = page.locator("table.cal_table td")
                count = await cells.count()
                for i in range(count):
                    cell = cells.nth(i)
                    img = cell.locator("img")
                    if await img.count() > 0:
                        alt = await img.first.get_attribute("alt") or ""
                        if any(x in alt for x in ["一部", "空き", "△", "○"]):
                            day = await cell.locator(".cal_day").inner_text()
                            found_vacancies.append(f"【{facility_name}】{day}日({alt})")
                            print(f"  [発見] {day}日: {alt}")
            except:
                pass

        # 巡回開始
        for target in targets:
            print(f">>> {target['name']} をチェック中...")
            try:
                # 接続エラー対策：リトライを強化
                success = False
                for i in range(2):
                    try:
                        await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="commit", timeout=60000)
                        success = True
                        break
                    except:
                        await asyncio.sleep(10)
                
                if not success:
                    print(f"  ! 接続できません。サイトがダウンしているか遮断されています。")
                    await page.screenshot(path=f"error_connection.png")
                    continue

                # メニュー操作（スマホ版の挙動に合わせる）
                for step in ["施設の空き状況", "利用目的から", "屋内スポーツ", "バドミントン"]:
                    await page.get_by_role("link", name=step).click(force=True)
                    await asyncio.sleep(2)

                # 施設・部屋選択
                await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                await asyncio.sleep(2)
                await page.locator(f"a:has-text('{target['room']}')").first.click(force=True)
                
                # 1ヶ月分だけを最速でチェック（まずは今月分！）
                await check_current_page(target['name'])
                
            except Exception as e:
                print(f"  ! エラー発生。画像を保存します。")
                await page.screenshot(path=f"error_{target['name']}.png")
                continue

        # 通知
        if found_vacancies:
            send_notification(found_vacancies)
            print(f"通知完了: {len(found_vacancies)} 件")
        else:
            print("本日のチェック終了。空きは見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom】三橋・大宮の空き(△)を発見！"
    body = "予約サイトに以下の空きがあります。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
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
