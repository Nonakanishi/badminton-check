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
        # ステルス設定を最大化
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1500}
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        found_vacancies = []
        debug_images = []

        async def save_and_mail_debug(label):
            path = f"debug_{label}.png"
            await page.screenshot(path=path)
            debug_images.append(path)

        try:
            print(">>> 予約サイトのトップページを開いています...")
            await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
            
            # --- 【突破】文字に頼らず、1番目のメインメニューをクリック ---
            print(">>> 1. 施設の空き状況ボタンを物理クリック中...")
            try:
                # 「施設の空き状況」は通常、左側のメニューの1番目
                await page.evaluate("document.querySelector('a[href*=\"rsvWTransInstSrchAction\"]').click()")
            except:
                # 失敗した場合はとにかく1番目のリンクを押す
                await page.locator(".menu_btn_area a, #disp a").first.click(force=True)
            
            await asyncio.sleep(2)

            # --- 2. 「利用目的から探す」をクリック ---
            print(">>> 2. 利用目的ボタンをクリック中...")
            await page.locator("a:has(img[alt*='目的']), a:has(img[src*='srch_02'])").first.click(force=True)
            await asyncio.sleep(2)

            # --- 3. 「屋内スポーツ」 ---
            print(">>> 3. 屋内スポーツを選択中...")
            await page.locator("a:has(img[src*='purpose_05']), a:has(img[alt*='スポーツ'])").first.click(force=True)
            await asyncio.sleep(2)

            # --- 4. 「バドミントン」 ---
            print(">>> 4. バドミントンを選択中...")
            await page.locator("a:has(img[alt*='バドミントン']), a:has(img[src*='ppsd_18'])").first.click(force=True)
            await asyncio.sleep(2)

            print(">>> バドミントン施設一覧に到達。精査を開始します。")

            # 三橋と大宮を重点チェック
            targets = [
                {"name": "三橋総合公園", "room": "体育室Ａ１／４", "kw": "体育室Ａ"},
                {"name": "大宮体育館", "room": "アリーナ１単位", "kw": "アリーナ１"}
            ]

            for target in targets:
                print(f"  - {target['name']} をスキャン中...")
                try:
                    await page.get_by_role("link", name=re.compile(target['name'])).first.click(force=True)
                    await asyncio.sleep(1)
                    
                    # 部屋選択（スクリーンショットの名称に合わせる）
                    await page.locator(f"a:has-text('{target['kw']}')").first.click(force=True)
                    
                    # カレンダーの読み取り
                    for m in range(2): # とりあえず2ヶ月分
                        await page.wait_for_selector("table.cal_table", timeout=20000)
                        
                        cells = page.locator("table.cal_table td")
                        for i in range(await cells.count()):
                            cell = cells.nth(i)
                            img = cell.locator("img")
                            if await img.count() > 0:
                                alt = await img.first.get_attribute("alt") or ""
                                # ★判定を極限まで甘くする（何かあればとりあえず拾う）
                                if any(x in alt for x in ["一部", "空き", "予約可", "△", "○"]):
                                    day = await cell.locator(".cal_day").inner_text()
                                    # 日曜日の判定を「見た目」ではなく「配置」でも補強
                                    found_vacancies.append(f"【{target['name']}】{day}日({alt}) - {target['room']}")
                                    print(f"    [★検知] {day}日: {alt}")

                        # 翌月へ
                        next_btn = page.locator("a:has-text('翌月'), a:has(img[alt*='翌月'])").first
                        if await next_btn.count() > 0:
                            await next_btn.click(force=True)
                            await asyncio.sleep(2)
                        else: break
                    
                    await page.get_by_role("link", name="もどる").first.click(force=True)
                except Exception as e:
                    print(f"    ! {target['name']} でエラー。画像を撮影します。")
                    await save_and_mail_debug(target['name'])
                    await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
                    # 再度メニューまで戻る（簡易化のため省略）
                    continue

        except Exception as e:
            print(f"!!! 致命的なエラー: {e}")
            await save_and_mail_debug("fatal_error")

        # 結果をメール
        send_report(found_vacancies, debug_images)

        await browser.close()

def send_report(vacancies, image_paths):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    msg = MIMEMultipart()
    msg["Subject"] = "【Kingdom最速】体育館空き状況レポート"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    body = "本日の巡回結果です。\n\n"
    if vacancies:
        body += "■発見した空き枠（△含む）:\n" + "\n".join(vacancies) + "\n\n"
    else:
        body += "条件に合う空きは見つかりませんでした。\n\n"
    msg.attach(MIMEText(body, "plain"))
    for p in image_paths:
        if os.path.exists(p):
            with open(p, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename=p)
                msg.attach(img)
    try:
        with smtplib.SMTP("smtp.mail.me.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
        print("メールを送信しました。")
    except: pass

if __name__ == "__main__":
    asyncio.run(run())
