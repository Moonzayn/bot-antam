import asyncio
import re
import json
import logging
import os
from datetime import datetime, timedelta
from patchright.async_api import async_playwright


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

RATE_LIMITED = "RATE_LIMITED"

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


async def check_rate_limit(page) -> bool:
    try:
        swal = page.locator("#swal2-title:has-text('Error')")
        if await swal.is_visible(timeout=1500):
            text = await swal.text_content()
            logging.warning(f"Rate limited: {text.strip()}")
            ok_btn = page.locator(".swal2-confirm, button:has-text('OK')")
            await ok_btn.first.click()
            await page.wait_for_timeout(1000)
            await page.goto("https://antrean.logammulia.com/antrean")
            await page.wait_for_selector("#site", timeout=10000)
            return True
    except:
        pass
    return False


def input_jam():
    while True:
        j = input("Target jam buka (HH:MM or HH:MM:SS): ").strip()
        parts = j.split(":")
        if len(parts) == 2 and re.match(r"^\d{2}:\d{2}$", j):
            h, m = int(parts[0]), int(parts[1])
            s = 0
        elif len(parts) == 3 and re.match(r"^\d{2}:\d{2}:\d{2}$", j):
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            print("Format salah! Gunakan HH:MM (contoh: 08:30) atau HH:MM:SS (contoh: 08:30:15)")
            continue
        if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
            return h, m, s
        print("Format salah! Gunakan HH:MM (contoh: 08:30) atau HH:MM:SS (contoh: 08:30:15)")


def next_target(h: int, m: int, s: int = 0) -> datetime:
    now = datetime.now()
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
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

        try:
            kuota_habis = page.locator("h2:has-text('Kuota Tidak Tersedia')")
            if await kuota_habis.is_visible(timeout=5000):
                logging.warning(f"{belm}: Kuota tidak tersedia, coba backup...")
                continue
        except:
            pass

        try:
            kuota_ada = page.locator("h2:has-text('Kuota Tersedia')")
            if await kuota_ada.is_visible(timeout=3000):
                sisa = page.locator("span.badge.bg-success")
                if await sisa.is_visible(timeout=1000):
                    sisa_text = await sisa.text_content()
                    logging.info(f"{belm}: {sisa_text.strip()}")
                else:
                    logging.info(f"{belm}: Kuota tersedia!")
        except:
            pass

        try:
            form_pool = page.locator("form[action*='masuk-pool']")
            if await form_pool.is_visible(timeout=3000):
                logging.info(f"{belm}: Form antrean siap!")
                return ctx, page, belm
        except:
            pass

        try:
            wakda = page.locator("#wakda")
            if await wakda.is_visible(timeout=3000):
                logging.info(f"{belm}: Slot tersedia!")
                return ctx, page, belm
        except:
            pass

        logging.warning(f"{belm}: Halaman antrean tidak dikenali, coba backup...")
        continue

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
    last_fetch_check = datetime.now()
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

            if (datetime.now() - last_fetch_check).total_seconds() >= 30:
                form_remote = await page.evaluate("""async () => {
                    try {
                        const resp = await fetch(window.location.href, { credentials: 'include' });
                        const html = await resp.text();
                        return html.includes('Kuota Tersedia')
                            || html.includes('masuk-pool')
                            || html.includes('Ambil Antrean');
                    } catch { return false; }
                }""")
                if form_remote:
                    logging.info("Form terdeteksi via background fetch! Reload page...")
                    await page.reload()
                    await page.wait_for_timeout(2000)
                    return
                last_fetch_check = datetime.now()

            has_form = await page.evaluate("""() => {
                return document.querySelector('h2:has-text("Kuota Tersedia")') !== null
                    || document.querySelector('form[action*="masuk-pool"]') !== null
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
# KEEP ALIVE BELM (standby di halaman BELM tanpa Tampilkan Butik)
# ============================================================

async def keep_alive_belm(page, target_dt: datetime, email: str, password: str):
    last_check = datetime.now()
    logging.info(f"Keep alive BELM sampai {target_dt.strftime('%H:%M:%S')}")

    while datetime.now() < target_dt:
        sisa = (target_dt - datetime.now()).total_seconds()
        if sisa <= 3:
            break

        try:
            if (datetime.now() - last_check).total_seconds() >= 30:
                still_ok = await page.evaluate("""() => {
                    return document.querySelector('#site') !== null
                        || document.querySelector('a[href*="logout"]') !== null
                }""")
                if not still_ok:
                    logging.warning("Session expired saat standby BELM. Relogin...")
                    ok = await do_login(page, email, password)
                    if ok:
                        await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
                        await page.wait_for_timeout(5000)
                last_check = datetime.now()
        except Exception as e:
            logging.warning(f"Keep alive BELM error: {e}")

        await asyncio.sleep(5)
    logging.info("Target waktu tiba, lanjut eksekusi...")


# ============================================================
# SUBMIT AT TARGET (pilih BELM, Tampilkan Butik, submit)
# ============================================================

async def submit_at_target(page, belm_list: list, cfg: dict):
    for attempt in range(1, 4):
        for belm in belm_list:
            logging.info(f"Percobaan {attempt}: {belm}")
            await select_belm_at_page(page, belm)

            try:
                form_pool = page.locator("form[action*='masuk-pool']")
                if await form_pool.is_visible(timeout=5000):
                    logging.info(f"{belm}: Form antrean siap!")
                    result = await race_submit(page)
                    if result == RATE_LIMITED:
                        logging.warning(f"Rate limited percobaan {attempt}/3")
                        await asyncio.sleep(attempt * 5)
                        break
                    if result:
                        return result
                    continue
            except:
                pass

            try:
                wakda = page.locator("#wakda")
                if await wakda.is_visible(timeout=3000):
                    logging.info(f"{belm}: Slot tersedia!")
                    result = await race_submit(page)
                    if result == RATE_LIMITED:
                        logging.warning(f"Rate limited percobaan {attempt}/3")
                        await asyncio.sleep(attempt * 5)
                        break
                    if result:
                        return result
                    continue
            except:
                pass

            try:
                kuota = page.locator("h2:has-text('Kuota Tidak Tersedia')")
                if await kuota.is_visible(timeout=3000):
                    logging.warning(f"{belm}: Kuota tidak tersedia, coba backup...")
                    continue
            except:
                pass

            logging.info(f"{belm}: Form belum siap, keep alive...")
            next_hour = datetime.now() + timedelta(hours=1)
            await keep_alive_loop(page, next_hour, belm, cfg["email"], cfg["password"])
            result = await race_submit(page)
            if result == RATE_LIMITED:
                await asyncio.sleep(attempt * 5)
                break
            if result:
                return result

    return None


# ============================================================
# MODE 6: AUTO WAR V2 (standby di BELM)
# ============================================================

async def mode_auto_war_v2(cfg):
    belm_list = pilih_belm()
    h, m, s = input_jam()
    target_dt = next_target(h, m, s)

    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M:%S')}")
    print(f">>> BELM: {', '.join(belm_list)}\n")

    await countdown_standby(target_dt)

    p, browser = await start_browser()
    ctx = await browser.new_context()
    page = await ctx.new_page()

    ok = await do_login(page, cfg["email"], cfg["password"])
    if not ok:
        await browser.close()
        await p.stop()
        return

    await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
    await page.wait_for_timeout(5000)
    print(f">>> Login selesai. URL: {page.url}")
    await save_session(ctx)

    await keep_alive_belm(page, target_dt, cfg["email"], cfg["password"])

    for wave in range(1, 4):
        result = await submit_at_target(page, belm_list, cfg)
        if result:
            break
        logging.warning(f"Wave {wave} gagal, tunggu 30 detik sebelum coba lagi...")
        await asyncio.sleep(30)

    if result:
        print(f"\n>>> ANTREAN BERHASIL!")
        print(f"    Queue: {result.get('queue_id', '?')}")
        print(f"    Code:  {result.get('code', '?')}")
        print(f"    Nama:  {result.get('name', '?')}")
    else:
        print(f"\n>>> Gagal mendapatkan antrean")

    await asyncio.sleep(3000)
    await browser.close()
    await p.stop()


# ============================================================
# RACE SUBMIT
# ============================================================

async def race_submit(page):
    logging.info("=== RACE SUBMIT ===")

    try:
        ok_btn = page.locator("a.btn-text-primary:has-text('OK')")
        if await ok_btn.is_visible(timeout=2000):
            await ok_btn.click()
            await page.wait_for_timeout(500)
    except:
        pass

    # Phase 1: Pilih slot & submit ambil antrean
    try:
        wakda = page.locator("#wakda")
        await wakda.wait_for(state="visible", timeout=5000)
        options = await wakda.locator("option:not([disabled])").all()
        available = [o for o in options if await o.get_attribute("value") and await o.get_attribute("value") != ""]
        if not available:
            logging.warning("Tidak ada slot waktu yang tersedia")
            return None

        first = available[0]
        val = await first.get_attribute("value")
        slot_text = await first.text_content()

        await page.evaluate("""(v) => {
            const sel = document.querySelector('#wakda');
            if (sel) {
                sel.removeAttribute('onchange');
                sel.value = v;
            }
        }""", val)
        logging.info(f"Slot dipilih: {slot_text.strip()}")
        await page.wait_for_timeout(300)

        logging.info("Menyelesaikan Turnstile di form antrean...")
        ok = await click_turnstile_checkbox(page)
        if not ok:
            logging.warning("Turnstile form antrean tidak terdeteksi, lanjut submit...")
        await page.wait_for_timeout(500)

        logging.info("Klik Ambil Antrean...")
        submit_btn = page.locator('button:has-text("Ambil Antrean"):not([disabled])')
        await submit_btn.click()
        await page.wait_for_timeout(5000)

        if await check_rate_limit(page):
            return RATE_LIMITED
    except Exception as e:
        logging.warning(f"Tidak ada form antrean: {e}")

    # Phase 2: Verify PIN / math captcha (redirect /masuk-pool)
    try:
        aritmetika = page.locator("#aritmetika")
        if await aritmetika.is_visible(timeout=5000):
            label = page.locator("h3")
            text = await label.text_content() or ""
            answer = solve_math(text.strip())
            await aritmetika.fill(answer)
            logging.info(f"PIN math: {text.strip()} -> {answer}")

            verify_btn = page.locator('button[type="submit"]:has-text("Verify")')
            await verify_btn.click()
            await page.wait_for_timeout(5000)

            if await check_rate_limit(page):
                return RATE_LIMITED
        else:
            logging.info("Tidak ada math captcha, mungkin modal langsung muncul")
    except Exception as e:
        logging.info(f"Tidak ada halaman verifikasi: {e}")

    # Phase 3: Parse result modal
    try:
        await page.wait_for_selector("#DialogBasic h1.mb-1", timeout=10000)
        await page.wait_for_timeout(1000)
    except:
        logging.warning("Modal antrean tidak muncul")
        return None

    details = {}
    try:
        details["queue_id"] = await page.locator("#DialogBasic h1.mb-1").text_content()
        details["queue_id"] = details["queue_id"].strip()

        qr_img = page.locator("#DialogBasic img[alt='QR Code']")
        details["qr_src"] = await qr_img.get_attribute("src")

        code_el = page.locator("#DialogBasic h2.mb-1")
        details["code"] = (await code_el.text_content()).strip()

        nik_el = page.locator("#DialogBasic h3.mb-1")
        details["nik"] = (await nik_el.first.text_content()).strip()

        name_el = page.locator("#DialogBasic h3.mb-1").nth(1)
        details["name"] = (await name_el.text_content()).strip()

        phone_el = page.locator("#DialogBasic h4.mb-1")
        if await phone_el.is_visible():
            details["phone"] = (await phone_el.text_content()).strip()
    except Exception as e:
        logging.error(f"Gagal parse detail antrean: {e}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"result_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(details, f, indent=2)
    logging.info(f"Hasil antrean disimpan ke {filename}")

    if "qr_src" in details:
        try:
            img_url = details["qr_src"]
            if img_url.startswith("/"):
                img_url = "https://antrean.logammulia.com" + img_url
            resp = await page.context.request.get(img_url)
            if resp.ok:
                qr_filename = f"qrcode_{timestamp}.png"
                with open(qr_filename, "wb") as f:
                    f.write(await resp.body())
                logging.info(f"QR code disimpan ke {qr_filename}")
        except Exception as e:
            logging.warning(f"Gagal download QR: {e}")

    return details


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
    h, m, s = input_jam()
    target_dt = next_target(h, m, s)

    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M:%S')}")
    print(f">>> BELM: {', '.join(belm_list)}\n")

    p, browser = await start_browser()
    ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
    if not ctx:
        await browser.close()
        await p.stop()
        return

    print(f">>> Login selesai. URL: {page.url}")
    await save_session(ctx)

    form_ready = await page.evaluate("""() => {
        return document.querySelector('form[action*="masuk-pool"]') !== null
            && document.querySelector('#wakda option:not([disabled])') !== null
    }""")
    if form_ready:
        logging.info("Form & slot sudah siap! Submit langsung...")
        result = await race_submit(page)
    else:
        logging.info("Form belum siap. Tutup browser, lanjut countdown...")
        await browser.close()
        await p.stop()

        await countdown_standby(target_dt)

        p, browser = await start_browser()
        ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
        if not ctx:
            await browser.close()
            await p.stop()
            return

        print(f">>> Login fase-2 selesai. URL: {page.url}")
        await save_session(ctx)

        await keep_alive_loop(page, target_dt, active_belm, cfg["email"], cfg["password"])
        result = await race_submit(page)

    if result:
        print(f"\n>>> ANTREAN BERHASIL!")
        print(f"    Queue: {result.get('queue_id', '?')}")
        print(f"    Code:  {result.get('code', '?')}")
        print(f"    Nama:  {result.get('name', '?')}")
    else:
        print(f"\n>>> Gagal mendapatkan antrean")

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
    h, m, s = input_jam()
    target_dt = next_target(h, m, s)

    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M:%S')}")
    print(f">>> BELM: {', '.join(belm_list)}\n")

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

    form_ready = await page.evaluate("""() => {
        return document.querySelector('form[action*="masuk-pool"]') !== null
            && document.querySelector('#wakda option:not([disabled])') !== null
    }""")
    if form_ready:
        logging.info("Form & slot sudah siap! Submit langsung...")
        result = await race_submit(page)
    else:
        logging.info("Form belum siap. Tutup browser, lanjut countdown...")
        await browser.close()
        await p.stop()

        await countdown_standby(target_dt)

        p, browser = await start_browser()
        ctx, page, active_belm = await login_and_prepare(browser, cfg, belm_list)
        if not ctx:
            await browser.close()
            await p.stop()
            return

        url = page.url
        print(f"\n>>> URL Tiket (fase-2): {url}")
        with open(URL_TIKET_FILE, "w") as f:
            f.write(url + "\n")

        await save_session(ctx)

        await keep_alive_loop(page, target_dt, active_belm, cfg["email"], cfg["password"])
        result = await race_submit(page)

    if result:
        print(f"\n>>> ANTREAN BERHASIL!")
        print(f"    Queue: {result.get('queue_id', '?')}")
        print(f"    Code:  {result.get('code', '?')}")
        print(f"    Nama:  {result.get('name', '?')}")
    else:
        print(f"\n>>> Gagal mendapatkan antrean")

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

    url = page.url
    print(f">>> URL: {url}")

    try:
        modal = page.locator("#DialogBasic h1.mb-1")
        if await modal.is_visible(timeout=3000):
            qid = (await modal.text_content()).strip()
            print(f">>> Antrean aktif: {qid}")
    except:
        pass

    try:
        kuota_habis = page.locator("h2:has-text('Kuota Tidak Tersedia')")
        if await kuota_habis.is_visible(timeout=3000):
            print(">>> Status: Kuota tidak tersedia")
    except:
        pass

    try:
        wakda = page.locator("#wakda")
        if await wakda.is_visible(timeout=2000):
            opts = await wakda.locator("option:not([disabled])").all()
            avail = [o for o in opts if await o.get_attribute("value") and await o.get_attribute("value") != ""]
            if avail:
                print(f">>> Slot tersedia: {len(avail)}")
                for a in avail:
                    txt = (await a.text_content()).strip()
                    print(f"    - {txt}")
            else:
                print(">>> Semua slot penuh")
    except:
        pass

    input("\nTekan Enter untuk tutup browser...")
    await browser.close()
    await p.stop()


# ============================================================
# MAIN
# ============================================================

def show_menu():
    print("""
  ======================================
         ANTAM BOT -- PLAN-A
  ======================================
   1. Login (simpan session)
   2. Auto war (full flow)
   3. Ekstrak URL tiket
   4. Ekstrak URL + Auto war
   5. Cek kuota tiket
   6. Auto war V2 (standby di BELM)
  ======================================
""")

async def run():
    with open("config.json") as f:
        cfg = json.load(f)

    show_menu()
    pilihan = input("Pilih mode (1-6): ").strip()

    modes = {
        "1": mode_login_only,
        "2": mode_auto_war,
        "3": mode_extract_url,
        "4": mode_extract_and_war,
        "5": mode_cek_kuota,
        "6": mode_auto_war_v2,
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
