# Design: Detik (Seconds) Support for Target Time

## Summary

Add optional seconds support (`HH:MM:SS`) to the target time input, so users can set a precise time like `06:30:02` instead of only `HH:MM`.

## Requirements

- Accept both `HH:MM` and `HH:MM:SS` formats
- If `HH:MM` is given, seconds default to `00`
- Validate ranges: hours 00-23, minutes 00-59, seconds 00-59
- All existing modes (auto war, extract URL, etc.) must continue to work

## Changes

### `bot.py` and `war.py` — identical changes in both files

#### 1. `input_jam()`

| Aspect | Current | New |
|--------|---------|-----|
| Regex | `r"^\d{2}:\d{2}$"` | `r"^\d{2}:\d{2}(:\d{2})?$"` |
| Validation | Check jam (00-23), menit (00-59) | Add detik (00-59) |
| Return | `(hh, mm)` as ints | `(hh, mm, ss)` as ints |

#### 2. `next_target(hhmm)`

Changed to `next_target(hh, mm, ss=0)`.

Internally use `datetime.now().replace(hour=hh, minute=mm, second=ss, microsecond=0)` instead of `datetime.strptime(f"{hh}:{mm}", "%H:%M")`.

Weekend-skip logic unchanged.

#### 3. Callers

Every call to `input_jam()` that previously did:
```python
hh, mm = input_jam()
target = next_target(hh, mm)
```
becomes:
```python
hh, mm, ss = input_jam()
target = next_target(hh, mm, ss)
```

Callers that pass stored values to `next_target` also updated.

## Files Modified

- `bot.py` — input_jam(), next_target(), and ~3 call sites
- `war.py` — same functions and call sites

## Testing

- Run the menu system, verify `06:30` works (backward compatible)
- Run with `06:30:02`, verify target time includes seconds
- Verify validation rejects invalid values (e.g., `25:00`, `06:61`, `06:30:61`)
