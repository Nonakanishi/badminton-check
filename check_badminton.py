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
        # タイムアウトを90秒に延長（1月1日の混雑対策）
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        page.set_default_timeout(90000) 
        
        found_vacancies = []

        # 施設リスト：キーワードだけで検索するように簡略化
        targets = [
            {"name": "鈴谷公民館", "room": "多目的", "filter": False},
            {"name": "岸町公民館", "room": "体育館", "filter": False},
            {"name": "三橋総合公園", "room": "体育室|競技場", "filter": True},
            {"name": "浦和西体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "与野体育館", "room": "アリーナ|競技場", "filter": True},
            {"name": "大宮体育館", "room": "アリーナ１|アリーナ２|アリーナ", "filter": True},
            {"name": "浦和駒場体育館", "room": "競技場|アリーナ", "filter": True},
            {"name": "サイデン化学アリーナ", "room": "サブアリーナ|アリーナ", "filter": True}
        ]

        async def check_current_page(facility_name, filter_time):
            # カレンダーの表示を待つ
            await page.wait_for_selector("table.cal_table", timeout=30000)
            calendar_table = page.locator("table.cal_table")
            
            month_label = page.locator("td.cal_month, .cal_month_area")
            month_text = await month_label.first.inner_text() if await month_label.count() > 0 else ""
            month_text = month_text.strip().replace("\n", "")

            cells = calendar_table.locator("td")
            for i in range(await cells.count()):
                cell = cells.nth(i)
                # △(一部空き)を最優先で検知
                vacancy_icons = cell.locator("img[alt*='空き'], img[alt*='一部'], img[alt*='予約可']")
                
                if await vacancy_icons.count() > 0:
                    day_text = await cell.locator(".cal_day").inner_text()
                    alt_text = await vacancy_icons.first.get_attribute("alt")
                    
                    class_attr = await cell.get_attribute("class") or ""
                    is_weekend = any(x in class_attr for x in ["cal_sun", "cal_sat", "cal_holiday"])

                    if not filter_time or is_weekend:
                        found_vacancies.append(f"【{facility_name}】{month_text}{day_text}日({alt_text})")
                        print(f"  [発見] {month_text}{day_text}日: {alt_text}")

        # 巡回メイン
        for target in targets:
            print(f">>> {target['name']} を確認中...")
            try:
                # 混雑対策：トップページへのアクセスをリトライ
                for i in range(3):
                    try:
                        await page.goto("https://saitama.rsv.ws-scs.jp/web/", wait_until="domcontentloaded")
                        break
                    except:
                        await asyncio.sleep(5)

                await page.get_by_role("link", name="施設の空き状況").click()
                await page.get_by_role("link", name="利用目的から").click()
                await page.get_by_role("link", name="屋内スポーツ").click()
                await page.get_by_role("link", name="バドミントン").click()

                # 施設クリック（もし見つからなければ全リンクから探す）
                facility_link = page.get_by_role("link", name=re.compile(target['name']))
                await facility_link.first.click()
                
                # ★改善：部屋名のリンクを「キーワードが含まれるかどうか」で探す
                # リンクを全部取得して、キーワードが含まれるものを探してクリック
                links = page.locator("a")
                found_room = False
                for i in range(await links.count()):
                    link_text = await links.nth(i).inner_text()
                    if any(kw in link_text for kw in target['room'].split('|')):
                        await links.nth(i).click()
                        found_room = True
                        break
                
                if not found_room:
                    print(f"  ! 部屋名 '{target['room']}' が見つかりません。")
                    continue

                for _ in range(3):
                    await check_current_page(target['name'], target['filter'])
                    next_btn = page.get_by_role("link", name=re.compile("翌月|次の月"))
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await asyncio.sleep(2)
                    else:
                        break

            except Exception as e:
                print(f"  ! {target['name']} でエラー（混雑中）: {e}")
                continue 

        # 通知
        if found_vacancies:
            send_notification(found_vacancies)
        else:
            print("本日のチェック終了：条件に合う空きはありませんでした。")

        await context.close()
        await browser.close()

def send_notification(vacancies):
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not app_password: return

    subject = "【Kingdom速報】体育館の空きを発見！"
    body = "以下の空きが見つかりました。\n\n" + "\n".join(vacancies) + "\n\n▼予約サイト\nhttps://saitama.rsv.ws-scs.jp/web/"
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
    except:
        print("メール送信失敗")

if __name__ == "__main__":
    asyncio.run(run())
