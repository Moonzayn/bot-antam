import asyncio
import re
import logging
from patchright.async_api import async_playwright
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EMAIL = "pangkassobo@gmail.com"
PASSWORD = "198456z"
BELM = "Bintaro"

def solve_math(text: str) -> str:
    nums = list(map(int, re.findall(r"\d+", text)))
    if "ditambah" in text or "+" in text:
        return str(sum(nums))
    if "dikali" in text or "x" in text:
        return str(nums[0] * nums[1]) if len(nums) >= 2 else str(nums[0])
    if "dikurang" in text:
        return str(abs(nums[0] - nums[1])) if len(nums) >= 2 else str(nums[0])
    return str(sum(nums)) if nums else "0"

async def run():
    async with async_playwright() as p:
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
        for i, f in enumerate(frames):
            logging.info(f"Frame {i}: {f.url[:80] if f.url else 'None'}")

        for f in frames:
            try:
                math_inp = await f.query_selector("input#aritmetika, input[name='aritmetika']")
                if math_inp:
                    logging.info(f"Form ditemukan di frame {f.url[:60]}")
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
                        logging.info("Login berhasil diklik!")

                    await page.wait_for_timeout(5000)
                    break
            except Exception as e:
                logging.warning(f"Frame error: {e}")

        logging.info("Klik Menu Antrean...")
        await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
        await page.wait_for_timeout(5000)
        logging.info(f"Redirect ke: {page.url}")

        await page.wait_for_selector("#site", timeout=10000)

        option_value = await page.locator(f"#site option:has-text('{BELM}')").get_attribute("value")
        await page.locator("#site").select_option(option_value)
        logging.info(f"BELM dipilih: {BELM}")

        await page.locator('button:has-text("Tampilkan Butik")').click()
        logging.info("Tampilkan Butik diklik!")

        await page.wait_for_timeout(5000)

        await browser.close()

asyncio.run(run())
