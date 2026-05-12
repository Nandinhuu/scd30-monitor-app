from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from data_source import DataSource


@dataclass(frozen=True)
class BleDeviceInfo:
    name: str
    address: str


class BleScanner(QObject):
    scan_finished = Signal(list)
    error = Signal(str)

    def scan(self, timeout: float = 5.0) -> None:
        threading.Thread(target=self._scan_thread, args=(timeout,), daemon=True).start()

    def _scan_thread(self, timeout: float) -> None:
        try:
            from bleak import BleakScanner

            devices = asyncio.run(BleakScanner.discover(timeout=timeout))
            result = [
                BleDeviceInfo(name=device.name or "Unknown BLE device", address=device.address)
                for device in devices
            ]
            self.scan_finished.emit(result)
        except Exception as exc:
            self.error.emit(f"BLE scan failed: {exc}")


class BLEDataSource(DataSource):
    def __init__(
        self,
        address: str,
        notify_characteristic_uuid: str,
        write_characteristic_uuid: str,
    ) -> None:
        super().__init__()
        self.address = address
        self.notify_characteristic_uuid = notify_characteristic_uuid
        self.write_characteristic_uuid = write_characteristic_uuid
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client = None
        self._connected = False
        self._buffer = bytearray()

    def connect_source(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def disconnect_source(self) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect_async(), self._loop)

    def send_line(self, line: str) -> None:
        if not self._loop or not self._loop.is_running() or not self._connected:
            self.error.emit("BLE is not connected")
            return
        asyncio.run_coroutine_threadsafe(self._send_async(line), self._loop)

    def is_connected(self) -> bool:
        return self._connected

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_async())
        self._loop.run_forever()

    async def _connect_async(self) -> None:
        try:
            from bleak import BleakClient

            self._client = BleakClient(self.address, disconnected_callback=self._on_disconnected)
            await self._client.connect()
            await self._client.start_notify(self.notify_characteristic_uuid, self._on_notify)
            self._connected = True
            self.connected.emit()
            self.log_message.emit(f"BLE connected: {self.address}")
        except Exception as exc:
            self.error.emit(f"BLE connection failed: {exc}")
            self._connected = False

    async def _disconnect_async(self) -> None:
        try:
            if self._client and self._client.is_connected:
                try:
                    await self._client.stop_notify(self.notify_characteristic_uuid)
                except Exception:
                    pass
                await self._client.disconnect()
        except Exception as exc:
            self.error.emit(f"BLE disconnect failed: {exc}")
        finally:
            self._connected = False
            self.disconnected.emit()
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)

    async def _send_async(self, line: str) -> None:
        if not self._client or not self._client.is_connected:
            self.error.emit("BLE is not connected")
            return
        payload = (line.rstrip("\r\n") + "\n").encode("utf-8")
        try:
            await self._client.write_gatt_char(self.write_characteristic_uuid, payload, response=True)
            self.log_message.emit(f"> {line}")
        except Exception as exc:
            self.error.emit(f"BLE write failed: {exc}")

    def _on_notify(self, _sender: int, data: bytearray) -> None:
        self._buffer.extend(data)
        while b"\n" in self._buffer:
            raw, _, self._buffer = self._buffer.partition(b"\n")
            line = raw.decode("utf-8", errors="replace").strip("\r")
            if line:
                self.line_received.emit(line)

    def _on_disconnected(self, _client) -> None:
        self._connected = False
        self.disconnected.emit()
        self.log_message.emit("BLE disconnected")
