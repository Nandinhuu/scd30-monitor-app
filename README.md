# B-U585I-IOT02A SCD30 Data Monitor

Windows desktop app for a capstone gas-sensing project. The app connects to a
B-U585I-IOT02A Discovery kit through either ST-LINK Virtual COM Port or BLE,
shows live SCD30 measurements, plots real-time curves, and saves clean CSV logs.

## Features

- Serial connection through ST-LINK Virtual COM Port.
- BLE connection through a configurable ST example GATT service.
- Real-time display for timestamp, sample index, CO2, temperature, humidity, and UV level.
- Real-time chart with enable/disable switches for each curve.
- CSV logging with the required header.
- Command buttons for time sync, start, stop, reset, interval, target samples, and status.
- Connection heartbeat commands for firmware LED status control.
- Raw communication log and parsing error log.

## Install on Windows

1. Install Python 3.10 or newer from <https://www.python.org/downloads/windows/>.
2. Install the ST-LINK USB driver from STMicroelectronics if the COM port is not visible.
3. Open PowerShell in this project folder.
4. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

5. Install dependencies:

```powershell
pip install -r requirements.txt
```

6. Run the app:

```powershell
python main.py
```

## Serial Connection

Use a USB cable from the PC to the B-U585I-IOT02A `CN8 ST-LINK USB Micro-B`
connector.

Default serial settings:

- Baud rate: `115200`
- Data bits: `8`
- Parity: none
- Stop bits: `1`
- Flow control: none

In the app:

1. Select `Serial / ST-LINK VCP`.
2. Click `Refresh COM Ports`.
3. Select the ST-LINK COM port.
4. Click `Connect`.

## BLE Connection

BLE uses the onboard STM32WB5MMG module. No extra external wiring is needed.

The app needs two UUIDs from the board firmware:

- Notify characteristic UUID: board sends CSV/status lines to the app.
- Write characteristic UUID: app sends commands to the board.

How to find the UUIDs:

- Check the ST BLE example firmware source files.
- Or connect with ST BLE Sensor / nRF Connect and inspect the advertised GATT service.
- Copy the notify and write characteristic UUIDs into the BLE tab before connecting.

In the app:

1. Select `BLE`.
2. Click `Scan BLE Devices`.
3. Select the board.
4. Enter notify/write UUIDs.
5. Click `Connect`.

## Board Data Format

The board should send one CSV line per valid sample:

```csv
timestamp,sample_index,co2_ppm,temperature_c,humidity_rh,uv_level
2026-05-12 15:30:01,1,421.00,24.31,51.20,0.00
2026-05-12 15:30:03,2,424.00,24.33,51.10,0.00
```

The `uv_level` field is supported from the beginning. If the UV sensor is not
installed yet, the firmware may send `0.00`. If it omits the sixth field, the app
also defaults UV to `0.00`.

## App Commands Sent to Board

The app sends UTF-8 text commands terminated with newline:

```text
APP_HELLO
APP_DISCONNECT
HEARTBEAT
SYNC_TIME:yyyy-mm-dd hh:mm:ss
START
STOP
RESET
SET_INTERVAL:2000
SET_TARGET_SAMPLES:100
GET_STATUS
```

Expected board responses:

```text
APP_CONNECTED_OK
HEARTBEAT_OK
TIME_SYNC_OK
DATA_COLLECTION_START
DATA_COLLECTION_STOP
RESET_OK
INTERVAL_SET_OK
TARGET_SAMPLES_SET_OK
STATUS:WAITING_FOR_APP
STATUS:CONNECTED_IDLE
STATUS:COLLECTING
STATUS:ERROR
ERROR:message
```

## LED State Logic for Firmware

This app sends connection-management commands so the firmware can drive onboard
LEDs.

LED pins on B-U585I-IOT02A:

| LED | Color | MCU Pin | Active Level |
| --- | --- | --- | --- |
| LD7 | Green | PH7 | 0 = on |
| LD6 | Red | PH6 | 0 = on |

Recommended firmware states:

| State | LED Behavior | Meaning |
| --- | --- | --- |
| BOOTING | Red/green alternate blink for 1-2 seconds | Board is starting |
| WAITING_FOR_APP | Red slow blink, green off | Board powered, app not connected |
| CONNECTED_IDLE | Green solid, red off | App connected, not collecting |
| COLLECTING | Green slow blink, red off | Sampling is active |
| COLLECTION_COMPLETE | Green double blink, red off | Target sample count reached |
| ERROR | Red solid or fast blink, green off | Sensor, I2C, protocol, or output error |
| RESETTING | Red and green short flash | Reset command is being processed |

Connection rules:

- On `APP_HELLO`, enter `CONNECTED_IDLE` and reply `APP_CONNECTED_OK`.
- While connected, expect `HEARTBEAT` at least every 5 seconds.
- On `START`, enter `COLLECTING`.
- On `STOP`, enter `CONNECTED_IDLE`.
- On `APP_DISCONNECT` or heartbeat timeout, enter `WAITING_FOR_APP`.

## Hardware Pin Map

### PC to B-U585I-IOT02A

| PC Side | Board Side | Purpose |
| --- | --- | --- |
| USB | CN8 ST-LINK USB Micro-B | Power, debug, programming, Virtual COM Port |

The Virtual COM Port is connected to STM32U585 `USART1`.

### SCD30 to B-U585I-IOT02A, Arduino I2C

| SCD30 Pin | Board Pin | STM32 Pin / Function |
| --- | --- | --- |
| VDD | CN17 pin 4 / 3V3 | 3.3 V power |
| GND | CN17 pin 6 or 7 / GND | Ground |
| TX/SCL | CN13 pin 10 / SCL/D15 | PB8 / I2C1_SCL |
| RX/SDA | CN13 pin 9 / SDA/D14 | PB9 / I2C1_SDA |
| SEL | GND or floating | Select I2C mode |
| RDY | Not connected in v1 | Optional data-ready interrupt |
| PWM | Not connected in v1 | Optional PWM CO2 output |

### BLE

BLE uses the onboard STM32WB5MMG module and requires no external wiring.

### UV Sensor

The first software version reserves the `uv_level` CSV field and displays it.
Until a UV sensor model is selected, send `0.00`.

## CSV Logging

The app writes this header:

```csv
timestamp,sample_index,co2_ppm,temperature_c,humidity_rh,uv_level
```

Every valid sample is appended with numeric values only, without units. Resetting
the board clears the screen and chart but does not stop CSV logging.

## Development Notes

- `data_source.py` defines the communication abstraction.
- `serial_worker.py` implements ST-LINK VCP communication.
- `ble_worker.py` implements BLE communication.
- `data_model.py` parses incoming CSV samples.
- `csv_logger.py` writes CSV rows.
- `main.py` contains the PySide6 GUI.
