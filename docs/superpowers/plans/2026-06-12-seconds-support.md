# Detik (Seconds) Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Add optional seconds support (`HH:MM:SS`) to target time input, e.g. `06:30:02`.

**Architecture:** Two functions changed in both `bot.py` and `war.py`: `input_jam()` (accept optional seconds, return `(hh,mm,ss)`) and `next_target()` (accept `hh,mm,ss` instead of `"HH:MM"` string). All call sites updated.

**Tech Stack:** Python 3, regex, datetime

---

### Task 1: Modify `input_jam()` in `bot.py`

**Files:** Modify: `bot.py:100-107`

- [x] **Step 1: Edit the regex and validation**

Change from:
```python
def input_jam() -> str:
    while True:
        j = input("Target jam buka (HH:MM): ").strip()
        if re.match(r"^\d{2}:\d{2}$", j):
            h, m = map(int, j.split(":"))
            if 0 <= h <= 23 and 0 <= m <= 59:
                return j
        print("Format salah! Gunakan HH:MM (contoh: 08:30)")
```

To:
```python
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
```

- [x] **Step 2: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('bot.py', doraise=True)"`
Expected: no output (success)

- [x] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: input_jam supports optional seconds (HH:MM:SS) in bot.py"
```

---

### Task 2: Modify `next_target()` in `bot.py`

**Files:** Modify: `bot.py:110-118`

- [x] **Step 1: Change signature and body**

From:
```python
def next_target(hhmm: str) -> datetime:
    now = datetime.now()
    h, m = map(int, hhmm.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return target
```

To:
```python
def next_target(h: int, m: int, s: int = 0) -> datetime:
    now = datetime.now()
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return target
```

- [x] **Step 2: Verify syntax**
- [x] **Step 3: Commit**

---

### Task 3: Update call sites in `bot.py`

**Files:** Modify: `bot.py:526-531`, `bot.py:616-621`

- [x] **Step 1: Update `mode_auto_war()`**

From:
```python
    target_hhmm = input_jam()
    target_dt = next_target(target_hhmm)
    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M')}")
```

To:
```python
    h, m, s = input_jam()
    target_dt = next_target(h, m, s)
    print(f"\n>>> Target: {target_dt.strftime('%A %d %b %Y %H:%M:%S')}")
```

- [x] **Step 2: Update `mode_extract_and_war()`** — same change
- [x] **Step 3: Verify syntax**
- [x] **Step 4: Commit**

---

### Task 4: Modify `input_jam()` in `war.py`
- [x] Same as Task 1
- [x] Verify syntax
- [x] Commit

### Task 5: Modify `next_target()` in `war.py`
- [x] Same as Task 2
- [x] Verify syntax
- [x] Commit

### Task 6: Update call sites in `war.py`
- [x] `mode_auto_war_v2()`, `mode_auto_war()`, `mode_extract_and_war()`

### Task 7: Create feature branch and final commit
- [x] Branch created and committed
