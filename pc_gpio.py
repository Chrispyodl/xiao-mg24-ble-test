"""PC side of the MG24_ble.py demo: switch a GPIO pin on the XIAO MG24 over BLE.

This runs on desktop Python (not MicroPython) and needs bleak:  pip install bleak
In Thonny, select the local Python 3 interpreter, not the XIAO's MicroPython.

Each command sent is "<msg_no>,<port>,<pin>,<level>", e.g. "7,gpioc,3,1".
The XIAO notifies back "<msg_no>,OK" or "<msg_no>,Err".
"""
import asyncio

from bleak import BleakClient, BleakScanner

# Must match MG24_ble.py
SVC_UUID = "250f0001-7eea-4188-bc62-8b1fc867bbea"
CMD_UUID = "250f0002-7eea-4188-bc62-8b1fc867bbea"
RESP_UUID = "250f0003-7eea-4188-bc62-8b1fc867bbea"

DEFAULT_PIN = "gpioc,3"
SCAN_TIMEOUT = 10.0      # seconds
RESPONSE_TIMEOUT = 3.0   # seconds

STATES = {"high": 1, "on": 1, "1": 1, "low": 0, "off": 0, "0": 0}

msg_no = 0


def ask_command():
    """Prompt for pin and state; return ("gpioc,3", 1), or None to quit"""
    while True:
        pin = input(f"Pin [{DEFAULT_PIN}] (q to quit): ").strip().lower() or DEFAULT_PIN
        if pin == "q":
            return None
        state = input("State (high/low): ").strip().lower()
        if state == "q":
            return None
        if state in STATES:
            return pin, STATES[state]
        print("Please enter high or low")


async def wait_for_reply(responses, expected_no):
    """Return "OK"/"Err" from the reply carrying expected_no, skipping others"""
    while True:
        reply = await responses.get()
        number, _, status = reply.partition(",")
        if number == str(expected_no):
            return status
        print(f"(ignoring unexpected reply {reply!r})")


async def control(client):
    """Prompt and send commands; return True if the user quit, False if disconnected"""
    global msg_no
    responses = asyncio.Queue()

    def on_response(_, data):
        responses.put_nowait(bytes(data).decode(errors="replace"))

    await client.start_notify(RESP_UUID, on_response)
    print("Connected.  Press Enter at the Pin prompt to use the default.")

    while True:
        command = ask_command()
        if command is None:
            return True
        pin, level = command

        # input() blocks, so a disconnect while waiting at the prompt is only seen here
        if not client.is_connected:
            print("XIAO is no longer connected; command not sent")
            return False

        msg_no += 1
        text = f"{msg_no},{pin},{level}"

        # Drop any stale replies so we only match this command's answer
        while not responses.empty():
            responses.get_nowait()

        print(f"Sending {text!r}")
        await client.write_gatt_char(CMD_UUID, text.encode(), response=True)

        try:
            status = await asyncio.wait_for(wait_for_reply(responses, msg_no), RESPONSE_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"#{msg_no}: no response from XIAO")
            continue
        print(f"#{msg_no}: {status}")


async def main():
    while True:
        print("Scanning for the XIAO (MG24-IO)...")
        device = await BleakScanner.find_device_by_filter(
            lambda d, adv: SVC_UUID in adv.service_uuids,
            timeout=SCAN_TIMEOUT)
        if device is None:
            print("Not found; is MG24_ble.py running?  Retrying.")
            continue

        print(f"Connecting to {device.name} ({device.address})")
        try:
            async with BleakClient(
                    device,
                    disconnected_callback=lambda c: print("XIAO disconnected")) as client:
                if await control(client):
                    return  # User quit
        except Exception as e:
            print(f"Connection lost or failed: {str(e).strip()}")
        print("Reconnecting...")


asyncio.run(main())
