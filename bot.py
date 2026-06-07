import asyncio
import re
import json
import logging
from datetime import datetime, timedelta
from patchright.async_api import async_playwright
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BELM_OPTIONS = [
    "ATGM-Gedung Antam",
    "ATGM-Graha Dipta",
    "Butik Emas LM - Balikpapan",
    "Butik Emas LM - Bandung",
    "Butik Emas LM - Bekasi",
    "Butik Emas LM - Bintaro",
    "Butik Emas LM - Bogor",
    "Butik Emas LM - Denpasar",
    "Butik Emas LM - Djuanda",
    "Butik Emas LM - Gedung Antam",
    "Butik Emas LM - Graha Dipta",
    "Butik Emas LM - Makassar",
    "Butik Emas LM - Medan",
    "Butik Emas LM - Palembang",
    "Butik Emas LM - Pekanbaru",
    "Butik Emas LM - Puri Indah",
    "Butik Emas LM - Semarang",
    "Butik Emas LM - Serpong",
    "Butik Emas LM - Setiabudi One",
    "Butik Emas LM - Surabaya 1 Darmo",
    "Butik Emas LM - Surabaya 2 Pakuwon",
    "Butik Emas LM - Yogyakarta",
    "CNBC Indonesia Jogja Financial Fest",
    "Exhibition - BSI Tower",
]

LOGIN_BUFFER_SEC = 180  # login 3 menit sebelum target


def pilih_belm():
    print("\n=== PILIH CABANG BELM ===\n")
    for i, b in enumerate(BELM_OPTIONS, 1):
        print(f"  {i:>2}. {b}")
    while True:
        try:
            pilih = int(input(f"\nPilih nomor (1-{len(BELM_OPTIONS)}): "))
            if 1 <= pilih <= len(BELM_OPTIONS):
                return BELM_OPTIONS[pilih - 1]
        except ValueError:
            pass
        print("Input tidak valid!")


def solve_math(text: str) -> str:
    nums = list(map(int, re.findall(r"\d+", text)))
    if "ditambah" in text or "+" in text:
        return str(sum(nums))
    if "dikali" in text or "x" in text:
        return str(nums[0] * nums[1]) if len(nums) >= 2 else str(nums[0])
    if "dikurang" in text:
        return str(abs(nums[0] - nums[1])) if len(nums) >= 2 else str(nums[0])
    return str(sum(nums)) if nums else "0"


def input_jam() -> str:
    while True:
        j = input("Target jam buka (HH:MM): ").strip()
        if re.match(r"^\d{2}:\d{2}$", j):
            h, m = map(int, j.split(":"))
            if 0 <= h <= 23 and 0 <= m <= 59:
                return j
        print("Format salah! Gunakan HH:MM (contoh: 08:30)")


def next_target(hhmm: str) -> datetime:
    now = datetime.now()
    h, m = map(int, hhmm.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return target


async def countdown_standby(target_dt: datetime):
    login_time = target_dt - timedelta(seconds=LOGIN_BUFFER_SEC)
    now = datetime.now()
    if now >= login_time:
        return
    total_sisa = int((login_time - now).total_seconds())
    print(f"  Target: {target_dt.strftime('%A %d %b %Y %H:%M')}")
    print(f"  Login fase: {login_time.strftime('%H:%M:%S')} (T-3 menit)")
    print(f"  Total standby: {total_sisa // 60} menit\n")
    while datetime.now() < login_time:
        sisa = int((login_time - datetime.now()).total_seconds())
        menit = sisa // 60
        detik = sisa % 60
        print(f"  Standby: {menit}m {detik}s tersisa...")
        await asyncio.sleep(60)


async def launch_and_login(cfg: dict, belm: str):
    EMAIL = cfg["email"]
    PASSWORD = cfg["password"]

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=False, channel="chrome")
    ctx = await browser.new_context()
    page = await ctx.new_page()

    await page.goto("https://antrean.logammulia.com/login")
    await asyncio.sleep(3)

    async with ClickSolver(framework=FrameworkType.PATCHRIGHT, page=page) as solver:
        try:
            await solver.solve_captcha(
                captcha_container=page,
                captcha_type=CaptchaType.CLOUDFLARE_INTERSTITIAL,
            )
        except Exception as e:
            logging.info(f"Solver selesai: {e}")

    logging.info("Menunggu form login...")
    await page.wait_for_timeout(5000)

    try:
        await page.wait_for_selector("input#aritmetika, input[name='aritmetika']", timeout=10000)
        logging.info("Form login ditemukan!")
    except:
        logging.info("Form tidak ketemu di main frame, cek iframe...")

    frames = page.frames
    for f in frames:
        try:
            math_inp = await f.query_selector("input#aritmetika, input[name='aritmetika']")
            if math_inp:
                username = await f.query_selector("input[type='text'], input[name='username'], input[placeholder*='email' i]")
                if username:
                    await username.fill("")
                    await username.fill(EMAIL)

                password = await f.query_selector("input[type='password']")
                if password:
                    await password.fill(PASSWORD)

                label = await f.query_selector("label[for='aritmetika']")
                if label:
                    text = await label.text_content() or ""
                    answer = solve_math(text)
                    await math_inp.fill(answer)
                    logging.info(f"Math: {text.strip()} -> {answer}")

                btn = await f.query_selector("button:has-text('Log in'), button[type='submit']")
                if btn:
                    await btn.click()

                await page.wait_for_timeout(5000)
                break
        except Exception as e:
            logging.warning(f"Frame error: {e}")

    await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
    await page.wait_for_timeout(5000)

    await page.wait_for_selector("#site", timeout=10000)
    option_value = await page.locator(f"#site option:has-text('{BELM}')").get_attribute("value")
    await page.locator("#site").select_option(option_value)
    logging.info(f"Cabang: {BELM}")

    await page.locator('button:has-text("Tampilkan Butik")').click()
    await page.wait_for_timeout(3000)

    return p, browser, page


async def relogin(page, email: str, password: str, belm: str):
    logging.warning("Session expired! Relogin...")
    await page.goto("https://antrean.logammulia.com/login")
    await page.wait_for_timeout(3000)

    async with ClickSolver(framework=FrameworkType.PATCHRIGHT, page=page) as solver:
        try:
            await solver.solve_captcha(
                captcha_container=page,
                captcha_type=CaptchaType.CLOUDFLARE_INTERSTITIAL,
            )
        except Exception as e:
            logging.info(f"Solver selesai: {e}")

    await page.wait_for_timeout(5000)

    for f in page.frames:
        try:
            math_inp = await f.query_selector("input#aritmetika, input[name='aritmetika']")
            if math_inp:
                username = await f.query_selector("input[type='text'], input[name='username'], input[placeholder*='email' i]")
                if username:
                    await username.fill("")
                    await username.fill(email)

                password_el = await f.query_selector("input[type='password']")
                if password_el:
                    await password_el.fill(password)

                label = await f.query_selector("label[for='aritmetika']")
                if label:
                    text = await label.text_content() or ""
                    answer = solve_math(text)
                    await math_inp.fill(answer)

                btn = await f.query_selector("button:has-text('Log in'), button[type='submit']")
                if btn:
                    await btn.click()
                await page.wait_for_timeout(5000)
                break
        except:
            pass

    await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
    await page.wait_for_timeout(5000)

    await page.wait_for_selector("#site", timeout=10000)
    option_value = await page.locator(f"#site option:has-text('{belm}')").get_attribute("value")
    await page.locator("#site").select_option(option_value)

    await page.locator('button:has-text("Tampilkan Butik")').click()
    await page.wait_for_timeout(3000)


async def keep_alive_loop(page, target_dt: datetime, belm: str, email: str, password: str):
    last_check = datetime.now()
    last_url = page.url
    logging.info(f"Keep alive dimulai. URL: {last_url}")

    while datetime.now() < target_dt:
        sisa = (target_dt - datetime.now()).total_seconds()
        if sisa <= 30:
            logging.info("Mendekati target, beralih ke polling intensif")
            break

        try:
            current_url = page.url
            if current_url != last_url:
                logging.info(f"URL berubah: {last_url} -> {current_url}")
                last_url = current_url

            if (datetime.now() - last_check).total_seconds() >= 30:
                still_ok = await page.evaluate("""() => {
                    return document.querySelector('a[href*="logout"], a.btn-logout') !== null
                        || document.querySelector('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")') !== null
                }""")
                if not still_ok:
                    await relogin(page, email, password, belm)
                    last_url = page.url
                last_check = datetime.now()

            has_form = await page.evaluate("""() => {
                return document.querySelector('form[action*="masuk-pool"]') !== null
                    || document.querySelector('select[name*="time"], select[name*="slot"]') !== null
                    || document.querySelector('button:has-text("Ambil Antrean")') !== null
            }""")
            if has_form:
                logging.info("Form / slot terdeteksi! Segera submit...")
                return

            await page.evaluate("window.location.href")
        except Exception as e:
            logging.warning(f"Keep alive error: {e}")

        await asyncio.sleep(8)


async def race_submit(page):
    logging.info("=== RACE SUBMIT PHASE (placeholder) ===")
    await page.wait_for_timeout(3000)


async def run():
    with open("config.json") as f:
        cfg = json.load(f)

    belm = pilih_belm()
    target_hhmm = input_jam()
    target_dt = next_target(target_hhmm)

    print(f"\n>>> Target antrean: {target_dt.strftime('%A %d %b %Y %H:%M')}")
    print(f">>> BELM: {belm}\n")

    await countdown_standby(target_dt)

    p, browser, page = await launch_and_login(cfg, belm)
    print(f">>> Login selesai. URL: {page.url}")

    await keep_alive_loop(page, target_dt, belm, cfg["email"], cfg["password"])

    await race_submit(page)

    await asyncio.sleep(3000)
    await browser.close()
    await p.stop()


asyncio.run(run())
