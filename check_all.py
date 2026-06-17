"""
Mode 7: Check all BELM branches availability.
Run: python check_all.py
"""
import asyncio
import json
import logging
from datetime import datetime
from war import (
    start_browser, do_login, select_belm_at_page,
    BELM_OPTIONS, save_session
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


async def check_all_belm(cfg):
    p, browser = await start_browser()
    ctx = await browser.new_context()
    page = await ctx.new_page()

    ok = await do_login(page, cfg["email"], cfg["password"])
    if not ok:
        print("Login gagal!")
        await browser.close()
        await p.stop()
        return

    await page.locator('a.btn.btn-primary.btn-lg:has-text("Menu Antrean")').first.click()
    await page.wait_for_timeout(5000)
    await save_session(ctx)

    print(f"\n{'='*60}")
    print(f"  CHECK ALL CABANG BELM")
    print(f"  {datetime.now().strftime('%A %d %b %Y %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = []

    for i, belm in enumerate(BELM_OPTIONS, 1):
        print(f"  [{i:>2}/{len(BELM_OPTIONS)}] {belm}... ", end="", flush=True)
        try:
            await select_belm_at_page(page, belm)

            kuota_habis = page.locator("h2:has-text('Kuota Tidak Tersedia')")
            if await kuota_habis.is_visible(timeout=5000):
                print("Kuota tidak tersedia")
                results.append((belm, "Kuota tidak tersedia"))
                continue

            kuota_ada = page.locator("h2:has-text('Kuota Tersedia')")
            if await kuota_ada.is_visible(timeout=3000):
                sisa = page.locator("span.badge.bg-success")
                if await sisa.is_visible(timeout=1000):
                    sisa_text = await sisa.text_content()
                    print(f"Kuota tersedia ({sisa_text.strip()})")
                    results.append((belm, f"Kuota tersedia ({sisa_text.strip()})"))
                else:
                    print("Kuota tersedia")
                    results.append((belm, "Kuota tersedia"))
                continue

            wakda = page.locator("#wakda")
            if await wakda.is_visible(timeout=3000):
                options = await wakda.locator("option:not([disabled])").all()
                available = [o for o in options if await o.get_attribute("value") and await o.get_attribute("value") != ""]
                if available:
                    slots = [(await a.text_content()).strip() for a in available]
                    print(f"Slot: {', '.join(slots)}")
                    results.append((belm, f"Slot tersedia: {', '.join(slots)}"))
                else:
                    print("Semua slot penuh")
                    results.append((belm, "Slot penuh"))
                continue

            form_pool = page.locator("form[action*='masuk-pool']")
            if await form_pool.is_visible(timeout=3000):
                print("Form antrean siap")
                results.append((belm, "Form antrean siap"))
                continue

            print("Status tidak diketahui")
            results.append((belm, "Tidak diketahui"))

        except Exception as e:
            print(f"Error: {e}")
            results.append((belm, f"Error: {e}"))

        await page.wait_for_timeout(1000)

    print(f"\n{'='*60}")
    print(f"  RINGKASAN")
    print(f"{'='*60}\n")

    tersedia = [r for r in results if any(k in r[1] for k in ["Kuota tersedia", "Slot", "Form antrean siap"])]
    habis = [r for r in results if r[1] in ("Kuota tidak tersedia", "Slot penuh")]
    unknown = [r for r in results if r not in tersedia and r not in habis]

    if tersedia:
        status = "TERSEDIA"
        print(f"  [{status}] ({len(tersedia)}):")
        for nama, s in tersedia:
            print(f"     - {nama}")
    if habis:
        print(f"\n  [TIDAK TERSEDIA] ({len(habis)}):")
        for nama, s in habis:
            print(f"     - {nama}")
    if unknown:
        print(f"\n  [TIDAK DIKETAHUI] ({len(unknown)}):")
        for nama, s in unknown:
            print(f"     - {nama} ({s})")

    print(f"\n{'='*60}\n")

    with open("check_all_result.json", "w") as f:
        json.dump([{"cabang": n, "status": s} for n, s in results], f, indent=2)
    print("  Hasil disimpan ke check_all_result.json")

    input("\n  Tekan Enter untuk tutup browser...")
    await browser.close()
    await p.stop()


async def main():
    with open("config.json") as f:
        cfg = json.load(f)
    await check_all_belm(cfg)


if __name__ == "__main__":
    asyncio.run(main())
