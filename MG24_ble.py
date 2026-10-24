import bluetooth
import time
from machine import Pin
from micropython import const

# BLE GPIO peripheral for the Seeed XIAO MG24 (Zephyr MicroPython).
#
# Uses the low-level 'bluetooth' module directly: this firmware has the GATT
# server calls (gatts_*) but no GATT client and no aioble.
#
# This firmware is built without f-strings: use str.format() instead.
#
# Protocol (UTF-8 text, keep commands under 20 bytes):
#   PC writes to the command characteristic:   "<msg_no>,<port>,<pin>,<level>"
#       e.g. "42,gpioc,3,1"  -> set gpioc pin 3 high, message number 42
#   XIAO notifies on the response characteristic: "<msg_no>,OK" or "<msg_no>,Err"
#       msg_no is "?" if it couldn't be read from the command.

BLE_NAME = "MG24-IO"  # Short so name + 128-bit UUID fit in one advert packet

# Custom 128-bit UUIDs, same family as pico_a.py
BLE_SVC_UUID = bluetooth.UUID("250f0001-7eea-4188-bc62-8b1fc867bbea")
BLE_CMD_UUID = bluetooth.UUID("250f0002-7eea-4188-bc62-8b1fc867bbea")
BLE_RESP_UUID = bluetooth.UUID("250f0003-7eea-4188-bc62-8b1fc867bbea")

BLE_ADVERTISING_INTERVAL = 100000  # microseconds (100 ms); spec minimum is 20 ms
BLE_CMD_BUFFER = 64
ADVERTISING_RETRY_MS = 500

# Only these (port, pin) pairs can be driven over BLE.  They start low.
ALLOWED_PINS = (("gpioc", 3),)

RESP_OK = "OK"
RESP_ERR = "Err"

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_UUID128_COMPLETE = const(0x07)
_ADV_TYPE_NAME = const(0x09)
_ADV_FLAGS_LE_GENERAL_NO_BREDR = const(0x06)
_ADV_MAX_LEN = const(31)

ble = bluetooth.BLE()
cmd_handle = None
resp_handle = None
pins = {}
connections = set()
pending = []  # (conn_handle, data) queued by ble_irq, handled in main()
advertise_pending = False  # Set by ble_irq on disconnect, handled in main()

def adv_field(adv_type, value):
    """ One length/type/value field of an advertising payload """
    return bytes((len(value) + 1, adv_type)) + value

def build_adv_payload():
    """ Flags + name + service UUID, checked against the 31-byte limit """
    payload = (adv_field(_ADV_TYPE_FLAGS, bytes((_ADV_FLAGS_LE_GENERAL_NO_BREDR,)))
               + adv_field(_ADV_TYPE_NAME, BLE_NAME.encode())
               + adv_field(_ADV_TYPE_UUID128_COMPLETE, bytes(BLE_SVC_UUID)))
    if len(payload) > _ADV_MAX_LEN:
        raise ValueError("Advertising payload is {} bytes; shorten BLE_NAME".format(len(payload)))
    return payload

ADV_PAYLOAD = build_adv_payload()

def start_advertising():
    """ Start advertising; return False if the stack isn't ready yet.  Zephyr
    gives ENOMEM until the previous connection's slot has been released. """
    try:
        ble.gap_advertise(BLE_ADVERTISING_INTERVAL, adv_data=ADV_PAYLOAD)
    except OSError as e:
        print("Advertising not ready ({}), retrying".format(e))
        return False
    print("{} advertising".format(BLE_NAME))
    return True

def setup_pins():
    """ Create an output for each allowed pin, starting low """
    for port, pin_no in ALLOWED_PINS:
        pin = Pin((port, pin_no), Pin.OUT)
        pin.value(0)
        pins[(port, pin_no)] = pin

def handle_command(data):
    """ Parse "<msg_no>,<port>,<pin>,<level>", set the pin, return the response """
    # Raw bytes repr, so hidden spaces/newlines/non-ASCII show up as escapes
    print("Received {} ({} bytes)".format(data, len(data)))
    msg_no = "?"
    try:
        parts = [p.strip() for p in data.decode().split(",")]
        msg_no = str(int(parts[0]))
        if len(parts) != 4:
            raise ValueError("expected msg_no,port,pin,level")

        port = parts[1].lower()
        pin_no = int(parts[2])
        level = int(parts[3])
        if level not in (0, 1):
            raise ValueError("level must be 0 or 1, not {}".format(level))

        pin = pins.get((port, pin_no))
        if pin is None:
            raise ValueError("{},{} is not an allowed pin".format(port, pin_no))

        pin.value(level)
        print("#{}: {},{} set {}".format(msg_no, port, pin_no, "high" if level else "low"))
        return "{},{}".format(msg_no, RESP_OK)

    except Exception as e:
        print("Command {} failed: {}".format(data, e))
        return "{},{}".format(msg_no, RESP_ERR)

def send_response(conn_handle, response):
    """ Store the response (so it can be read) and notify it to the central """
    payload = response.encode()
    ble.gatts_write(resp_handle, payload)
    if conn_handle not in connections:
        return
    try:
        # Pass the data explicitly: on Zephyr, notify without it sends an empty value
        ble.gatts_notify(conn_handle, resp_handle, payload)
    except Exception as e:
        print("Error notifying response: {}".format(e))

def ble_irq(event, data):
    """ Keep this short: commands and re-advertising are handled in main() """
    global advertise_pending
    if event == _IRQ_CENTRAL_CONNECT:
        conn_handle, _, _ = data
        connections.add(conn_handle)
        advertise_pending = False
        ble.gap_advertise(None)  # One central at a time
        print("Connected (handle {})".format(conn_handle))
    elif event == _IRQ_CENTRAL_DISCONNECT:
        conn_handle, _, _ = data
        connections.discard(conn_handle)
        print("Disconnected (handle {})".format(conn_handle))
        advertise_pending = True
    elif event == _IRQ_GATTS_WRITE:
        conn_handle, attr_handle = data
        if attr_handle == cmd_handle:
            pending.append((conn_handle, ble.gatts_read(cmd_handle)))

def main():
    """ Main function """
    global cmd_handle, resp_handle, advertise_pending

    setup_pins()

    ble.active(True)
    ((cmd_handle, resp_handle),) = ble.gatts_register_services((
        (BLE_SVC_UUID, (
            (BLE_CMD_UUID, bluetooth.FLAG_WRITE),
            (BLE_RESP_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY),
        )),
    ))
    ble.gatts_set_buffer(cmd_handle, BLE_CMD_BUFFER)
    ble.gatts_write(resp_handle, b"")
    ble.irq(ble_irq)

    try:
        _, addr = ble.config('mac')
        print("{} address {}".format(BLE_NAME, ":".join("{:02X}".format(b) for b in addr)))
    except Exception:
        pass

    advertise_pending = True
    last_advertise_try = time.ticks_add(time.ticks_ms(), -ADVERTISING_RETRY_MS)

    try:
        while True:
            if (advertise_pending and
                    time.ticks_diff(time.ticks_ms(), last_advertise_try) >= ADVERTISING_RETRY_MS):
                last_advertise_try = time.ticks_ms()
                if start_advertising():
                    advertise_pending = False

            while pending:
                conn_handle, data = pending.pop(0)
                send_response(conn_handle, handle_command(data))
            time.sleep_ms(10)
    finally:
        # Leave the outputs low and the radio off when stopped from Thonny
        for pin in pins.values():
            pin.value(0)
        ble.active(False)

main()
