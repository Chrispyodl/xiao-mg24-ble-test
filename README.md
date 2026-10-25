# XIAO MG24 BLE GPIO demo

A learning project: finding out how Bluetooth Low Energy (BLE) works on the [Seeed XIAO MG24](https://www.seeedstudio.com/) running Zephyr MicroPython, and how to
send simple messages between two devices.  It's groundwork for more useful projects later.

The XIAO acts as a BLE **peripheral**.  A PC connects to it and tells it to switch a GPIO pin (an LED on D3, which Zephyr calls `gpioc,3`) high or low.  The XIAO replies `OK` or `Err`.

```
 PC (pc_gpio.py)  ── "42,gpioc,3,1" ──►  XIAO MG24 (MG24_ble.py)
                  ◄──── "42,OK" ───────      LED on D3 switches on
```

## Status

Working and tested:  The PC connects and switches the LED on `gpioc,3` high and low.  It has also been tested from the nRF Connect phone app.

Two recent fixes have been committed but not yet tested on the board (see "Notes and gotchas" below).  This is a hobby project, so expect rough edges.

## Files

| File | Runs on | Language |
|---|---|---|
| `MG24_ble.py` | XIAO MG24 | Zephyr MicroPython (no f-strings, no `aioble`) |
| `pc_gpio.py` | A PC | Desktop Python 3 + [`bleak`](https://github.com/hbldh/bleak) |

Both use the same custom 128-bit UUID family
(`250f000N-7eea-4188-bc62-8b1fc867bbea`, where 1 = service, 2 = command, 3 = response).

## How it works

**On the XIAO (`MG24_ble.py`)**

- Advertises as `MG24-IO` and accepts one connection at a time.
- **Command characteristic** (write): `"<msg_no>,<port>,<pin>,<level>"`, for example
  `"42,gpioc,3,1"`. Keep it under 20 bytes.
- **Response characteristic** (read/notify): `"<msg_no>,OK"` or `"<msg_no>,Err"`.
- Only pins listed in `ALLOWED_PINS` can be driven. They start low and are set low again when the script stops.  Right now that list contains `gpioc,3` only.

**On the PC (`pc_gpio.py`)**

Scans for the service, connects, subscribes to the response characteristic, then asks you for a pin and a level in a loop.  Press Enter to use `gpioc,3` or `q` to quit.  If the connection drops, it scans and reconnects.

## Running it

1. Copy `MG24_ble.py` to the XIAO as `main.py` (for example with Thonny) and power the board from USB.
2. On the PC, install `bleak` (`pip install bleak`) and run `pc_gpio.py`.
3. Follow the prompts.

## Notes and gotchas (XIAO MG24, MicroPython 1.27.0-preview)

These cost me some time, so they might save you some:

- **No f-strings.** They raise a `SyntaxError` on this firmware. Use `str.format()`.
- **No `aioble`**, and `bluetooth.BLE()` has the GATT *server* calls (`gap_advertise`, `gatts_*`, `irq`) but no GATT *client* calls (`gattc_*`).  The XIAO can only be a peripheral.
- **Pins** use the Zephyr style:  `Pin(("gpioc", 3), Pin.OUT)`.
- **`gatts_notify(conn, handle)` with no data sends an empty notification.**  Always pass the data explicitly.  A fix for this is in, but not yet tested on the board.
- **`gap_advertise()` can raise `OSError` (ENOMEM)** right after a disconnect, until Zephyr frees the connection slot.  The script doesn't advertise from the IRQ handler.  It sets a flag and the main loop retries.
- **Stopping and re-running in Thonny can leave the Bluetooth stack stuck.**  Power-cycling
  the board clears it.

## Security

There isn't any yet.  This is a learning demo:  Anyone in Bluetooth range can connect and switch the allowed pins.  Pairing and security are on my list of things to try.

## Ideas for next steps

- Open up more pins in `ALLOWED_PINS`
- Clearer per-field error messages from the XIAO
- Pairing and security

## Licence

Released under the MIT Licence (see `LICENSE`).  Please feel free to copy anything that's useful to you.

## A personal project

I'm sharing this so that like-minded people can get ideas from it. It's a personal learning project, so I'm **not accepting pull requests**. Questions and conversation are very welcome in Discussions, and you're free to fork it and take it in your own direction.
