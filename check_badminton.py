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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()
        page.set_default_timeout(90000)

        found_vacancies = []

        # 巡回ターゲット
        targets = [
            {"name": "三橋総合公園", "room": "体育室Ａ", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "岸町公民館", "room": "体育館", "filter": False}
        ]

        try:
            print(">>> 予約サイトへ接続中...")
            await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="networkidle")
            
            # --- 手順を「番号指定」で突破：文字が消えていても進めます ---
            print(">>> メニューを突破中...")
            
            # 1. 「施設の空き状況」: 画面内の1番目のメインボタンをクリック
            await page.locator(".menu_btn_area a, #disp a").first.click(force=True)
            await page.wait_for_load_state("networkidle")

            # 2. 「利用目的から探す」: 2番目のボタンをクリック
            await page.locator(".menu_btn_area a, #disp a").nth(1).click(force=True)
            await page.wait_for_load_state("networkidle")

            # 3. 「屋内スポーツ」: およそ5番目のアイコン（画像認識を強化）
            sports_icon = page.locator("a:has(img[src*='05']), a:has(img[alt*='スポーツ']), a:has-text('屋内')").first
            if await sports_icon.count() > 0:
                await sports_icon.click(force=True)
            else:
                # 文字も画像も見えない場合、5番目のリンクを強引に叩く
                await page.locator("#disp a").nth(4).click(force=True)
            
            await page.wait_for_load_state("networkidle")

            # 4. 「バドミントン」: アイコンを直接指定
            badminton_icon = page.locator("a:has(img[alt*='バドミントン']), a:has-text('バド')").first
            if await badminton_icon.count() > 0:
                await badminton_icon.click(force=True)
            else:
                # 強行突破（リストの中のバドミントンの位置）
                await page.locator("#disp a").nth(0).click(force=True)

            print(">>> バドミントン施設一覧に到達しました。巡回を開始します。")

            # --- 施設巡回 ---
            for target in targets:
                try:
                    print(f"  - {target['name']} を確認中...")
                    # 施設名を部分一致で検索してクリック
                    facility_link = page.locator(f"a:has-text('{target['name']}')").first
                    await facility_link.click(force=True)
                    
                    # 部屋選択
                    room_kw = target['room'].split('|')[0]
                    await page.locator(f"a:has-text('{room_kw}')").first.click(force=True)

                    # 3ヶ月分チェック
                    for _ in range(3):
                        await page.wait_for_selector("table.cal_table", timeout=30000)
                        
                        # 空き検知ロジック
                        cells = page.locator("table.cal_table td")
                        for i in range(await cells.count()):
                            cell = cells.nth(i)
                            # △(一部空き)アイコンを逃さず拾う
                            img = cell.locator("img[alt*='一部'], img[alt*='空き'], img[alt*='予約可']")
                            if await img.count() > 0:
                                alt = await img.first.get_attribute("alt")
                                day = await cell.locator(".cal_day").inner_text()
                                if not target['filter'] or any(x in (await cell.get_attribute("class") or "") for x in ["sun", "sat", "holiday"]):
                                    found_vacancies.append(f"【{target['name']}】{day}日({alt})")
                                    print(f"    [★発見] {day}日: {alt}")

                        # 翌月へ
                        next_btn = page.locator("a:has-text('翌月'), a:has(img[alt*='翌月'])").first
                        if await next_btn.count() > 0:
                            await next_btn.click(force=True)
                            await asyncio.sleep(2)
                        else: break

                    # 一覧に戻る
                    await page.get_by_role("link", name="もどる").first.click(force=True)
                except:
                    # エラー時はトップからやり直さず、一覧に戻るか次へ
                    await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                    # 再度ナビゲーションが必要な場合はここに記述（今回は簡易化）
                    continue

        except Exception as e:
            print(f"!!! 巡回中にエラーが発生しました: {e}")

        # メール送信
        if found_vacancies:
            send_notification(found_vacancies)
        else:
            print("空き枠は見つかりませんでした。")

        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return
    subject = "【Kingdom速報】体育館の空き枠(△)を発見！"
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
        print(f"メール送信完了: {len(vacancies)} 件")
    except: pass

if __name__ == "__main__":
    asyncio.run(run())
