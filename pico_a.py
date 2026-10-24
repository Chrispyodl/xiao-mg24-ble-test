import aioble
import bluetooth
import asyncio
from sys import exit

# IAM = "Central" # Change to 'Peripheral' or 'Central'
IAM = "Central"

if IAM not in ['Peripheral','Central']:
    print("IAM must be either Peripheral or Central")
    exit()

if IAM == "Central":
    IAM_SENDING_TO = "Peripheral"
else:
    IAM_SENDING_TO = "Central"

MESSAGE = f"Hello from {IAM}!"

# Custom 128-bit UUIDs (not Bluetooth SIG ones).  They share a base and differ
# in the first group, so they're easy to recognise in a scanner app.
#   Command:  Central writes a command, Peripheral receives it.
#   Response: Peripheral notifies "OK" or "Err" back to Central.
BLE_SVC_UUID = bluetooth.UUID("250f0001-7eea-4188-bc62-8b1fc867bbea")
BLE_CMD_UUID = bluetooth.UUID("250f0002-7eea-4188-bc62-8b1fc867bbea")
BLE_RESP_UUID = bluetooth.UUID("250f0003-7eea-4188-bc62-8b1fc867bbea")

RESP_OK = "OK"
RESP_ERR = "Err"

# Bluetooth parameters
BLE_NAME = f"{IAM}"  # You can dynamically change this if you want unique names
BLE_APPEARANCE = 0x0300
BLE_ADVERTISING_INTERVAL = 100000  # microseconds (100 ms); spec minimum is 20 ms
BLE_SCAN_LENGTH = 5000
BLE_INTERVAL = 30000
BLE_WINDOW = 30000
BLE_RESPONSE_TIMEOUT_MS = 2000
SEND_INTERVAL = 1

# state variables
message_count = 0

def encode_message(message):
    """ Encode a message to bytes """
    return message.encode('utf-8')

def decode_message(message):
    """ Decode a message from bytes """
    return message.decode('utf-8')

def handle_command(data):
    """ Act on a command from Central and return RESP_OK or RESP_ERR """
    try:
        command = decode_message(data)
    except UnicodeError:
        print(f"Bad command bytes: {data}")
        return RESP_ERR

    if not command:
        return RESP_ERR

    # TODO: parse the command and drive GPIO pins here
    print(f"{IAM} received: {command}")
    return RESP_OK

async def receive_commands_task(connection, command_char, response_char):
    """ Peripheral: wait for commands and reply to each with OK or Err """
    while connection.is_connected():
        try:
            _, data = await command_char.written(timeout_ms=1000)
        except asyncio.TimeoutError:
            # No command yet; loop round to re-check the connection
            continue

        reply = handle_command(data)
        try:
            response_char.write(encode_message(reply))
            response_char.notify(connection)
        except Exception as e:
            print(f"Error sending response: {e}")

async def send_commands_task(connection, command_char, response_char):
    """ Central: send a command, then wait for the OK/Err response """
    global message_count
    while connection.is_connected():
        message = f"{MESSAGE} {message_count}"
        message_count += 1
        print(f"sending {message}")

        try:
            await command_char.write(encode_message(message), response=True)
            reply = decode_message(
                await response_char.notified(timeout_ms=BLE_RESPONSE_TIMEOUT_MS))
            print(f"{IAM} sent: {message}, response {reply}")
        except asyncio.TimeoutError:
            print(f"Timeout waiting for response from {IAM_SENDING_TO}")
        except aioble.DeviceDisconnectedError:
            return
        except Exception as e:
            print(f"Error sending command: {e}")
            return

        await asyncio.sleep(SEND_INTERVAL)

async def run_peripheral_mode():
    """ Run the peripheral mode """

    # Set up the Bluetooth service and characteristics
    ble_service = aioble.Service(BLE_SVC_UUID)
    command_char = aioble.Characteristic(
        ble_service,
        BLE_CMD_UUID,
        write=True,
        capture=True,
    )
    response_char = aioble.Characteristic(
        ble_service,
        BLE_RESP_UUID,
        read=True,
        notify=True,
    )
    aioble.register_services(ble_service)

    while True:
        print(f"{BLE_NAME} starting to advertise")
        async with await aioble.advertise(
            BLE_ADVERTISING_INTERVAL,
            name=BLE_NAME,
            services=[BLE_SVC_UUID],
            appearance=BLE_APPEARANCE) as connection:
            print(f"{BLE_NAME} connected to another device: {connection.device}")

            await receive_commands_task(connection, command_char, response_char)
            print(f"{IAM} disconnected")

async def ble_scan():
    """ Scan for a BLE device with the matching name and service UUID """

    print(f"Scanning for BLE device named {IAM_SENDING_TO}...")

    async with aioble.scan(BLE_SCAN_LENGTH, interval_us=BLE_INTERVAL,
                           window_us=BLE_WINDOW, active=True) as scanner:
        async for result in scanner:
            if result.name() == IAM_SENDING_TO and BLE_SVC_UUID in result.services():
                print(f"found {result.name()} with service uuid {BLE_SVC_UUID}")
                return result
    return None

async def run_central_mode():
    """ Run the central mode """

    while True:
        # Scan for a device with the matching name and service UUID
        device = await ble_scan()

        if device is None:
            continue
        print(f"device is: {device}, name is {device.name()}")

        try:
            print(f"Connecting to {device.name()}")
            connection = await device.device.connect()
        except asyncio.TimeoutError:
            print("Timeout during connection")
            continue
        except Exception as e:
            print(f"Error connecting: {e}")
            await asyncio.sleep(1)
            continue

        print(f"{IAM} connected to {connection}")

        # Leaving this block disconnects, so every 'continue' cleans up
        async with connection:
            try:
                service = await connection.service(BLE_SVC_UUID)
                if service is None:
                    print(f"Service {BLE_SVC_UUID} not found")
                    continue
                command_char = await service.characteristic(BLE_CMD_UUID)
                response_char = await service.characteristic(BLE_RESP_UUID)
                if command_char is None or response_char is None:
                    print("Command/response characteristic not found")
                    continue
                await response_char.subscribe(notify=True)
            except asyncio.TimeoutError:
                print("Timed out discovering services/characteristics")
                continue
            except Exception as e:
                print(f"Error discovering services {e}")
                continue

            await send_commands_task(connection, command_char, response_char)
            print(f"{BLE_NAME} disconnected from {device.name()}")

async def main():
    """ Main function """
    if IAM == "Central":
        await run_central_mode()
    else:
        await run_peripheral_mode()

asyncio.run(main())
