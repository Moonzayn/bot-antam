# Race Submit + Queue Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the final race phase — detect queue issuance after "Tampilkan Butik", select time slot, submit, and parse QR code.

**Architecture:** The bot currently navigates to `/antrean?site=XX&t=TOKEN` after "Tampilkan Butik". The server auto-issues a queue ticket (JKT06-NNN) if quota is available, shown in a Bootstrap modal. Below the modal, a `masuk-pool` form lets the user select a time slot (`#wakda`) and confirm. The race submit phase must detect the modal, select an available slot, submit, and save the QR code.

**Tech Stack:** Patchright (Playwright), Python 3.14, asyncio

## Files

- **Modify:** `bot.py` — add `race_submit()`, fix kuota detection, add QR save
- **Create:** `result_TEMPLATE.json` — optional, not needed (results saved as JSON inline)

---

### Task 1: Fix kuota detection selector

**Files:**
- Modify: `bot.py:238-245` (login_and_prepare kuota check)

**Problem:** Current code checks `p.text-danger:has-text('Kuota antrean')`, but the actual "Kuota Tidak Tersedia" text is in `<h2 class="text-primary">`. Additionally, the page might show a different element when kuota IS available (the queue modal).

**Fix:** The correct detection approach: after "Tampilkan Butik" + 3s wait, check if the queue modal `#DialogBasic` with `h1` containing queue number (e.g., `JKT06-`) appears. If it appears, kuota was available. If the "Kuota Tidak Tersedia" `<h2>` is visible instead, kuota is unavailable.

Actually, looking at the HTML more carefully, the `#DialogBasic` modal is always in the HTML but may be hidden. When queue is issued, it's shown. When no queue, it stays hidden.

Better approach: check for the `masuk-pool` form AND an enabled `<select id="wakda">` option. If the form has enabled options in `#wakda`, kuota is available AND slots can be selected.

- [ ] **Step 1: Replace kuota check**

Replace the `login_and_prepare` kuota detection:

```python
# Old (lines ~238-245):
kuota = page.locator("p.text-danger:has-text('Kuota antrean')")
if await kuota.is_visible():
    logging.warning(f"{belm}: Kuota tidak tersedia, coba backup...")
    continue

logging.info(f"{belm}: Kuota tersedia!")
return ctx, page, belm
```

New:

```python
# Check if Kuota Tidak Tersedia heading is visible
try:
    kuota_habis = page.locator("h2:has-text('Kuota Tidak Tersedia')")
    if await kuota_habis.is_visible(timeout=5000):
        logging.warning(f"{belm}: Kuota tidak tersedia, coba backup...")
        continue
except:
    pass

# Check if form masuk-pool exists (indicates page loaded correctly)
try:
    form_pool = page.locator("form[action*='masuk-pool']")
    if await form_pool.is_visible(timeout=5000):
        logging.info(f"{belm}: Form antrean tersedia!")
        return ctx, page, belm
except:
    pass

# Fallback: check if #wakda dropdown exists anywhere
try:
    wakda = page.locator("#wakda")
    if await wakda.is_visible(timeout=3000):
        logging.info(f"{belm}: Slot waktu tersedia!")
        return ctx, page, belm
except:
    pass

logging.warning(f"{belm}: Halaman antrean tidak dikenali, coba backup...")
continue
```

- [ ] **Step 2: Verify the fix**

Run: `python bot.py` with mode 5
Expected: Correctly detects "Kuota Tidak Tersedia" OR detects form with available slot.

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "fix: perbaiki deteksi kuota, ganti selector ke h2 & form masuk-pool"
```

---

### Task 2: Implement race_submit

**Files:**
- Modify: `bot.py` — replace `race_submit()` placeholder

**Context:** After `keep_alive_loop` finishes (target time reached), the page should be at the `/antrean?site=XX&t=TOKEN` URL. The user needs to:
1. Check if `#DialogBasic` modal is showing (queue already issued)
2. If not, check `#wakda` for available slots
3. Select the first available slot from `#wakda`
4. Read the CSRF token from `input[name="csrf_test_name"]`
5. Submit the `masuk-pool` form
6. Wait for the modal to appear
7. Extract queue details (JKT code, QR image URL, NIK, name)
8. Save to `result_{timestamp}.json`
9. Download the QR image

- [ ] **Step 1: Write race_submit() implementation**

```python
async def race_submit(page):
    logging.info("=== RACE SUBMIT ===")

    # 1. Dismiss any existing modal (click OK)
    try:
        ok_btn = page.locator("a.btn-text-primary:has-text('OK')")
        if await ok_btn.is_visible(timeout=2000):
            await ok_btn.click()
            await page.wait_for_timeout(500)
    except:
        pass

    # 2. Check if #wakda exists and has available options
    try:
        wakda = page.locator("#wakda")
        await wakda.wait_for_selector(state="visible", timeout=5000)
        options = await wakda.locator("option:not([disabled])").all()
        available = [o for o in options if await o.get_attribute("value") and await o.get_attribute("value") != ""]
        if not available:
            logging.warning("Tidak ada slot waktu yang tersedia")
            return None

        # Select first available slot
        first = available[0]
        val = await first.get_attribute("value")
        await wakda.select_option(val)
        slot_text = await first.text_content()
        logging.info(f"Slot dipilih: {slot_text.strip()}")

        # 3. Read CSRF token
        csrf = await page.locator("input[name='csrf_test_name']").get_attribute("value")

        # 4. Click submit
        submit_btn = page.locator("button[type='submit']:not([disabled])")
        await submit_btn.first.click()
        await page.wait_for_timeout(5000)
    except Exception as e:
        logging.warning(f"Tidak ada form slot: {e}")

    # 5. Wait for queue modal to appear
    try:
        await page.wait_for_selector("#DialogBasic h1.mb-1", timeout=10000)
        await page.wait_for_timeout(1000)  # wait for QR to load
    except:
        logging.warning("Modal antrean tidak muncul")
        return None

    # 6. Extract queue details
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

        time_el = page.locator("#DialogBasic h4.mb-1")
        if await time_el.is_visible():
            details["waktu_kedatangan"] = (await time_el.text_content()).strip()
    except Exception as e:
        logging.error(f"Gagal parse detail antrean: {e}")

    # 7. Save result
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"result_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(details, f, indent=2)
    logging.info(f"Hasil antrean disimpan ke {filename}")

    # 8. Download QR image
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
```

- [ ] **Step 2: Integrate into mode functions**

In `mode_auto_war` and `mode_extract_and_war`, after `await race_submit(page)`, add summary print:

```python
result = await race_submit(page)
if result:
    print(f"\n>>> ANTREAN BERHASIL!")
    print(f"    Queue: {result.get('queue_id', '?')}")
    print(f"    Code:  {result.get('code', '?')}")
    print(f"    Nama:  {result.get('name', '?')}")
    print(f"    File:  result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
else:
    print("\n>>> Gagal mendapatkan antrean")
```

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: implement race submit, slot selection, QR parse & save"
```

---

### Task 3: Fix `mode_cek_kuota` to properly detect quota

**Files:**
- Modify: `bot.py` — `mode_cek_kuota`

**Problem:** Current `mode_cek_kuota` uses old kuota detection. Needs to align with Task 1 fix.

- [ ] **Step 1: Update mode_cek_kuota**

Make it consistent with the new `login_and_prepare` detection. Also restore the `input()` for interactive mode since this is a user-facing diagnostic tool.

```python
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

    # Check what's visible
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
            avail = [o for o in opts if await o.get_attribute("value")]
            if avail:
                print(f">>> Slot tersedia: {len(avail)}")
            else:
                print(">>> Semua slot penuh")
    except:
        pass

    input("\nTekan Enter untuk tutup browser...")
    await browser.close()
    await p.stop()
```

- [ ] **Step 2: Commit**

```bash
git add bot.py
git commit -m "fix: update mode_cek_kuota pakai deteksi baru"
```

---

### Task 4: Clean up temp hardcode and polish

**Files:**
- Modify: `bot.py` — restore interactive menu, remove TEMP hardcode

- [ ] **Step 1: Restore `pilih_belm()` and menu**

Replace TEMP hardcoded values back to interactive:

```python
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
```

And in `run()`:

```python
    pilihan = input("Pilih mode (1-5): ").strip()
```

- [ ] **Step 2: Add logging noise suppression back**

Add back the asyncio logger suppress in case the browser cleanup has issues:

```python
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
```

- [ ] **Step 3: Verify full flow**

Run `python bot.py` mode 5 — should prompt for BELM interactively, log in, detect kuota correctly.
Run `python bot.py` mode 1 — should prompt for BELM, log in, save session.

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "chore: restore interactive menu, cleanup temp hardcode"
```

---

### Task 5: Merge to war-tiket

**Files:**
- No code changes

- [ ] **Step 1: Merge branch**

```bash
git checkout war-tiket
git merge inspect-antrean-page
git push origin war-tiket
```

---

## Self-Review

**Spec coverage:**
- Task 1 covers fixing kuota detection — needed because current selector was wrong
- Task 2 covers full race_submit — modal detection, slot selection, form submission, QR parsing and download
- Task 3 updates mode_cek_kuota for diagnostics
- Task 4 restores interactive mode (cleanup)
- Task 5 merges to main dev branch

**Placeholder check:** No placeholders — all code blocks contain actual implementation code.

**Type consistency:** All function names match existing code (`race_submit`, `login_and_prepare`, `mode_cek_kuota`). Selectors match actual HTML structure verified from the page dump.
