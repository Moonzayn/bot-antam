import asyncio
import re
import json
import logging
import os
from datetime import datetime, timedelta
from patchright.async_api import async_playwright


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

SESSION_FILE = "session.json"
URL_TIKET_FILE = "url_tiket.txt"
LOGIN_BUFFER_SEC = 180

# ============================================================
# HELPERS
# ============================================================

def pilih_belm():
    print("\n=== PILIH CABANG BELM ===\n")
    for i, b in enumerate(BELM_OPTIONS, 1):
        print(f"  {i:>2}. {b}")
    while True:
        raw = input(f"\nPilih nomor (pisah koma untuk backup): ").strip()
        try:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
            hasil = []
            for idx in indices:
                if 1 <= idx <= len(BELM_OPTIONS):
                    hasil.append(BELM_OPTIONS[idx - 1])
            if hasil:
                print(f"  #1: {hasil[0]}")
                for j, h in enumerate(hasil[1:], 2):
                    print(f"  #{j}: {h} (backup)")
                return hasil
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


# ============================================================
# SESSION MANAGEMENT
# ============================================================

async def save_session(ctx):
    cookies = await ctx.cookies()
    with open(SESSION_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    logging.info(f"Session disimpan ke {SESSION_FILE}")


async def load_session(browser) -> "context|None":
    if not os.path.exists(SESSION_FILE):
        return None
    with open(SESSION_FILE) as f:
        cookies = json.load(f)
    ctx = await browser.new_context()
    await ctx.add_cookies(cookies)
    return ctx


async def is_session_valid(page) -> bool:
    try:
        await page.goto("https://antrean.logammulia.com/antrean")
        await page.wait_for_timeout(3000)
        if await page.locator("#site").is_visible():
            return True
        return False
    except:
        return False


# ============================================================
# BROWSER + LOGIN
# ============================================================

async def start_browser():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=False, channel="chrome")
    return p, browser


async def click_turnstile_checkbox(page) -> bool:
    for _ in range(15):
        has_token = await page.evaluate(
            """() => document.querySelector('input[name="cf-turnstile-response"]')?.value?.length > 0"""
        )
        if has_token:
            logging.info("Turnstile token already exists")
            return True
        try:
            turnstile_iframe = None
            for f in page.frames:
                if "challenges.cloudflare.com" in f.url and "/turnstile/" in f.url:
                    turnstile_iframe = f
                    break
            if not turnstile_iframe:
                await asyncio.sleep(1)
                continue
            checkbox = await turnstile_iframe.wait_for_selector(
                'input[type="checkbox"]', timeout=2000
            )
            if checkbox:
                await checkbox.click(timeout=3000)
        except:
            pass
        await asyncio.sleep(1)
    return False


async def do_login(page, email: str, password: str):
    await page.goto("https://antrean.logammulia.com/login")
    await asyncio.sleep(2)

    ok = await click_turnstile_checkbox(page)
    if not ok:
        logging.error("Turnstile gagal diselesaikan")
        return False

    for f in page.frames:
        try:
            math_inp = await f.query_selector("input#aritmetika, input[name='aritmetika']")
            if not math_inp:
                continue
            username = await f.query_selector("input[type='text'], input[name='username'], input[placeholder*='email' i]")
            if username:
                await username.fill("")
                await username.fill(email)

            pw = await f.query_selector("input[type='password']")
            if pw:
                await pw.fill(password)

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
            return True
        except:
            pass
    return False


async def select_belm_at_page(page, belm: str):
    try:
        await page.wait_for_selector("#site", timeout=5000)
    except:
        await page.goto("https://antrean.logammulia.com/antrean")
        await page.wait_for_selector("#site", timeout=10000)
    option_value = await page.locator(f"#site option:has-text('{belm}')").get_attribute("value")
    await page.locator("#site").select_option(option_value)
    logging.info(f"Cabang: {belm}")
    await page.locator('button:has-text("Tampilkan Butik")').click()
    await page.wait_for_timeout(3000)


async def login_and_prepare(browser, cfg: dict, belm_list: list):
    ctx = await browser.new_context()
    page = await ctx.new_page()

    ok = await do_login(page, cfg["email"], cfg["password"])
    if not ok:
        return None, None, None

    await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
    await page.wait_for_timeout(5000)

    for belm in belm_list:
        await select_belm_at_page(page, belm)

        kuota = page.locator("p.text-danger:has-text('Kuota antrean')")
        if await kuota.is_visible():
            logging.warning(f"{belm}: Kuota tidak tersedia, coba backup...")
            continue

        logging.info(f"{belm}: Kuota tersedia!")
        return ctx, page, belm

    logging.error("Semua BELM penuh atau error")
    return None, None, None


async def relogin(page, email: str, password: str, belm: str):
    logging.warning("Session expired! Relogin...")
    await page.goto("https://antrean.logammulia.com/login")
    await page.wait_for_timeout(3000)

    ok = await click_turnstile_checkbox(page)
    if not ok:
        return

    for f in page.frames:
        try:
            math_inp = await f.query_selector("input#aritmetika, input[name='aritmetika']")
            if not math_inp:
                continue
            username = await f.query_selector("input[type='text'], input[name='username'], input[placeholder*='email' i]")
            if username:
                await username.fill("")
                await username.fill(email)

            pw = await f.query_selector("input[type='password']")
            if pw:
                await pw.fill(password)

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
    await select_belm_at_page(page, belm)


# ============================================================
# KEEP ALIVE
# ============================================================

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
        except Exception as e:
            logging.warning(f"Keep alive error: {e}")

        await asyncio.sleep(8)


# ============================================================
# RACE SUBMIT (PLACEHOLDER)
# ============================================================

async def race_submit(page):
    logging.info("=== RACE SUBMIT PHASE (placeholder) ===")
    await page.wait_for_timeout(3000)


# ============================================================
# COUNTDOWN STANDBY
# ============================================================

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
        print(f"  Standby: {sisa // 60}m {sisa % 60}s tersisa...")
        await asyncio.sleep(60)


# ============================================================
# MODES
# ============================================================

async def mode_login_only(cfg):
    p, browser = await start_browser()
    ctx = await browser.new_context()
    page = await ctx.new_page()

    ok = await do_login(page, cfg["email"], cfg["password"])
    if ok:
        await save_session(ctx)
        print("\n>>> Login sukses. Session disimpan.")

    input("\nTekan Enter untuk tutup browser...")
    await browser.close()
    await p.stop()


async def mode_auto_war(cfg):
    belm_list = pilih_belm()
    target_hhmm = input_jam()
    target_dt = next_target(target_hhmm)

    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M')}")
    print(f">>> BELM: {', '.join(belm_list)}\n")

    await countdown_standby(target_dt)

    p, browser = await start_browser()

    ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
    if not ctx:
        await browser.close()
        await p.stop()
        return

    print(f">>> Login selesai. URL: {page.url}")

    await save_session(ctx)
    await keep_alive_loop(page, target_dt, active_belm, cfg["email"], cfg["password"])
    await race_submit(page)

    await asyncio.sleep(3000)
    await browser.close()
    await p.stop()


async def mode_extract_url(cfg):
    belm_list = pilih_belm()
    p, browser = await start_browser()

    ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
    if not ctx:
        await browser.close()
        await p.stop()
        return

    url = page.url
    print(f"\n>>> URL Tiket: {url}")
    with open(URL_TIKET_FILE, "w") as f:
        f.write(url + "\n")
    print(f">>> URL disimpan ke {URL_TIKET_FILE}")

    input("\nTekan Enter untuk tutup browser...")
    await browser.close()
    await p.stop()


async def mode_extract_and_war(cfg):
    belm_list = pilih_belm()
    target_hhmm = input_jam()
    target_dt = next_target(target_hhmm)

    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M')}")
    print(f">>> BELM: {', '.join(belm_list)}\n")

    await countdown_standby(target_dt)

    p, browser = await start_browser()

    ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
    if not ctx:
        await browser.close()
        await p.stop()
        return

    url = page.url
    print(f"\n>>> URL Tiket: {url}")
    with open(URL_TIKET_FILE, "w") as f:
        f.write(url + "\n")

    await save_session(ctx)
    await keep_alive_loop(page, target_dt, active_belm, cfg["email"], cfg["password"])
    await race_submit(page)

    await asyncio.sleep(3000)
    await browser.close()
    await p.stop()


async def mode_cek_kuota(cfg):
    belm_list = pilih_belm()
    p, browser = await start_browser()

    ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
    if not ctx:
        await browser.close()
        await p.stop()
        return

    print(f">>> URL: {page.url}")
    input("\nTekan Enter untuk tutup browser...")
    await browser.close()
    await p.stop()


# ============================================================
# MAIN
# ============================================================

def show_menu():
    print(r"""
  ╔══════════════════════════════════════╗
  ║         ANTAM BOT — PLAN-A           ║
  ╠══════════════════════════════════════╣
  ║  1. Login (simpan session)           ║
  ║  2. Auto war (full flow)             ║
  ║  3. Ekstrak URL tiket                ║
  ║  4. Ekstrak URL + Auto war           ║
  ║  5. Cek kuota tiket                  ║
  ╚══════════════════════════════════════╝
""")

async def run():
    with open("config.json") as f:
        cfg = json.load(f)

    show_menu()
    pilihan = input("Pilih mode (1-5): ").strip()

    modes = {
        "1": mode_login_only,
        "2": mode_auto_war,
        "3": mode_extract_url,
        "4": mode_extract_and_war,
        "5": mode_cek_kuota,
    }

    handler = modes.get(pilihan)
    if not handler:
        print("Pilihan tidak valid!")
        return

    try:
        await handler(cfg)
    except KeyboardInterrupt:
        pass
    finally:
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in others:
            if t.done():
                t.exception() if not t.cancelled() else None
            else:
                t.cancel()
        if others:
            await asyncio.wait(others, timeout=5)


if __name__ == "__main__":
    asyncio.run(run())
