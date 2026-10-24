## Project goal
A learning project: find out how Bluetooth LE works on the Seeed XIAO MG24 (Zephyr MicroPython) and how to exchange messages between two devices, as groundwork for more useful projects later.

The XIAO acts as a BLE peripheral that switches a GPIO pin (an LED on D3 = `gpioc,3`) high or low on command from a PC.  Each command carries a message number, port, pin and level; the XIAO replies `OK` or `Err` with the same message number.

## Where we're up to (last updated 2026-10-24)
- **Working and tested:** MG24_ble.py on the XIAO with pc_gpio.py on the Nobara PC: connects, and switches the LED on `gpioc,3` high and low.  Also tested earlier from the nRF Connect phone app.
- **Changed but NOT yet tested on the board** (committed anyway):
  - MG24_ble.py: `send_response()` now passes the data to `gatts_notify()`.  Before this, the PC received an empty notification (`''`), skipped it, and reported "no response from XIAO" even though the pin switched.  Expected after the fix: `#1: OK`.
  - pc_gpio.py: checks `client.is_connected` before sending, so powering off the XIAO while at the prompt prints "XIAO is no longer connected; command not sent" and reconnects, instead of a long D-Bus `UnknownObject` error.
- **Next steps (ideas, nothing agreed yet):**
  1. Test the two fixes above (copy MG24_ble.py to the XIAO as `main.py` again and power-cycle).
  2. Open up more pins in `ALLOWED_PINS` in MG24_ble.py.  Deliberately left as `gpioc,3` only for now.
  3. Possibly: clearer per-field error messages on the XIAO; pairing/security (currently anyone in range can connect).

## Machines and workflow
- The repo is on GitHub and is worked on from two computers.  Always `git pull` before starting and push when done, so either machine (and Claude on either) can pick up from here.  **This file is the shared record of progress**: Claude's own memory isn't synced between machines, so put anything worth keeping here.
- **Nobara 44 PC** (Fedora-based, Python 3.14): the main machine; the XIAO is connected here.  Runs Thonny for both the board and pc_gpio.py, with `bleak` installed for the local Python.
- **Mac laptop**: occasional editing only; no board access.  Its `.venv` (Python 3.9, git-ignored) has only pip/setuptools and isn't used by anything.
- There is no build system, test suite, or linter config.

## Testing
- I test manually using Thonny.  Don't try to run the scripts: the MicroPython ones only run on a board (`machine`, `bluetooth` don't exist on desktop Python), and pc_gpio.py is interactive and needs the board.  A syntax check with desktop Python (`python3 -c "import ast; ast.parse(open('file.py').read())"`) is fine.
- To run MG24_ble.py without Thonny attached, save it on the XIAO as `main.py` and power the board from USB.  Thonny can then use the local Python interpreter for pc_gpio.py (or allow multiple Thonny instances in Tools → Options → General to watch both).

## Files
| File | Runs on | Language |
|---|---|---|
| MG24_ble.py | XIAO MG24 | Zephyr MicroPython: **no f-strings**, no aioble |
| pc_gpio.py | Nobara PC | Desktop Python 3.14 + bleak; f-strings fine |
| pico_a.py | Raspberry Pi Pico (x2) | Pico MicroPython + aioble; f-strings fine |

All three use the same custom 128-bit UUID family (`250f000N-7eea-4188-bc62-8b1fc867bbea`; 1 = service, 2 = command, 3 = response).  If you change UUIDs in one file, change them in the others that talk to it.

## XIAO MG24 firmware facts
- MicroPython 1.27.0-preview, `zephyr-xiao_mg24`.  No `aioble`.
- `bluetooth.BLE()` has the GAP and GATT **server** calls (`gap_advertise`, `gatts_*`, `irq`) but **no GATT client** (`gattc_*`), so the XIAO can only be a peripheral.
- `bluetooth` provides the `FLAG_*` constants and `UUID`.
- **No f-strings** (SyntaxError at compile time); use `str.format()`.
- Pins use Zephyr-style `Pin(("gpioc", 3), Pin.OUT)` (devicetree port label + pin number).  Confirmed working.
- `gatts_notify(conn, handle)` without a data argument sends an **empty** notification on this firmware; always pass the data explicitly.
- `gap_advertise()` can raise `OSError` ENOMEM right after a disconnect (or a Thonny re-run while still connected) until Zephyr frees the connection slot.  MG24_ble.py never advertises from `ble_irq`; it sets `advertise_pending` and `main()` retries every `ADVERTISING_RETRY_MS`.
- Stopping and re-running the script in Thonny can leave the Bluetooth stack stuck (ENOMEM retries forever); `ble.active(False)` doesn't seem to fully reset it.  Power-cycling the board clears it.

## Hardware notes
- Flag any board-specific modules or calls (e.g. Pico's rp2, PIO) and suggest MG24 equivalents.
- Don't assume an API from another port exists on the MG24; ask or flag when unsure.

## MG24_ble.py: BLE GPIO peripheral (XIAO)

Uses the plain `bluetooth` module (no asyncio, no aioble); `main()` at module level starts it.  It advertises as `MG24-IO` with `BLE_SVC_UUID` in a single advertising packet, and accepts one central at a time.

- Command characteristic (`BLE_CMD_UUID`, write): `"<msg_no>,<port>,<pin>,<level>"`, e.g. `"42,gpioc,3,1"`.  Keep it under 20 bytes.
- Response characteristic (`BLE_RESP_UUID`, read/notify): `"<msg_no>,OK"` or `"<msg_no>,Err"` (`msg_no` is `"?"` if unreadable).
- Only pins listed in `ALLOWED_PINS` can be driven; they start low and are set low again when the script stops.
- Every received command is printed as raw bytes with its length (`Received b'...' (n bytes)`), so stray characters (e.g. from a phone keyboard) are visible.
- `ble_irq` only queues writes and sets `advertise_pending`; `main()` handles them, so pin, notify and advertise calls stay out of the IRQ handler.

## pc_gpio.py: PC client (desktop Python)

Runs on the Nobara PC in Thonny with the local Python interpreter, using `bleak` (BlueZ).  It scans for `SVC_UUID`, connects, subscribes to the response characteristic, then loops: prompts for pin (Enter = `gpioc,3`, `q` quits) and high/low, writes `"<msg_no>,<port>,<pin>,<level>"`, and waits up to `RESPONSE_TIMEOUT` for the reply with the matching `msg_no`.  On a lost connection it rescans and reconnects.

- `input()` blocks the asyncio loop, so a disconnect while at the prompt is only noticed when the next command is about to be sent.  Fine for this demo.

## pico_a.py: Pico BLE Central/Peripheral demo (reference)

Kept as a working reference; the Pico is no longer part of the target setup.  Keep it working unless I say otherwise.  Committed after fixes but not re-tested on the Picos since then.

One script serves both roles.  The `IAM` constant (`"Central"` or `"Peripheral"`) picks the role, so you flash two boards with the same file and change `IAM` on one of them.  `asyncio.run(main())` at module level starts it.

- **Peripheral** (`run_peripheral_mode`): registers a GATT service (`BLE_SVC_UUID`) with a write-only **command** characteristic (`BLE_CMD_UUID`, `capture=True`) and a read/notify **response** characteristic (`BLE_RESP_UUID`).  It advertises under the name `IAM`, and once connected loops in `receive_commands_task`: it waits on `command_char.written()`, calls `handle_command()`, and replies `"OK"` or `"Err"` by writing and notifying the response characteristic.  When the central disconnects, it advertises again.
- **Central** (`run_central_mode`): `ble_scan` looks for a device whose advertised name equals `IAM_SENDING_TO` and that advertises `BLE_SVC_UUID`.  The central connects, discovers both characteristics, subscribes to response notifications, and then loops in `send_commands_task`: it writes a command (with response) and waits on `response_char.notified()` for OK/Err.  When the peripheral disconnects, it scans again.
- Its message format (`"Hello from Central! N"` → `"OK"`) is not the MG24_ble.py protocol, so a Pico Central can't drive the XIAO as-is.

Gotchas:
- In `aioble`, a local (server-side) `Characteristic` uses synchronous `read()`/`write()`.  A remote (client-side) characteristic returned by `service.characteristic()` uses `await`able `read()`/`write()`.
- With `capture=True`, writes from the central are **not** stored in the characteristic's value; they are only delivered via `await characteristic.written()`, which returns `(connection, data)`.
- The 128-bit service UUID doesn't fit in the 31-byte advertising packet alongside the name `"Peripheral"`, so aioble moves it into the scan response.  The central must scan with `active=True` to see it.
- A local connection object is always truthy; use `connection.is_connected()` to detect a dropped link.
