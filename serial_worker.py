from __future__ import annotations

import threading
import time

import serial
from PySide6.QtCore import Signal
from serial.tools import list_ports

from data_source import DataSource


def available_serial_ports() -> list[str]:
    return [port.device for port in list_ports.comports()]


class SerialDataSource(DataSource):
    status_changed = Signal(str)

    def __init__(self, port: str, baud_rate: int = 115200) -> None:
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self._serial: serial.Serial | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def connect_source(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.2,
                write_timeout=1.0,
            )
        except serial.SerialException as exc:
            self.error.emit(f"Serial connection failed: {exc}")
            return

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self.connected.emit()
        self.log_message.emit(f"Serial connected: {self.port} @ {self.baud_rate}")

    def disconnect_source(self) -> None:
        self._stop_event.set()
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except serial.SerialException as exc:
                    self.error.emit(f"Serial close failed: {exc}")
        self.disconnected.emit()
        self.log_message.emit("Serial disconnected")

    def send_line(self, line: str) -> None:
        payload = (line.rstrip("\r\n") + "\n").encode("utf-8")
        with self._lock:
            if not self._serial or not self._serial.is_open:
                self.error.emit("Serial is not connected")
                return
            try:
                self._serial.write(payload)
                self._serial.flush()
            except serial.SerialException as exc:
                self.error.emit(f"Serial write failed: {exc}")
                self.disconnect_source()
                return
        self.log_message.emit(f"> {line}")

    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def _read_loop(self) -> None:
        buffer = bytearray()
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    ser = self._serial
                if not ser or not ser.is_open:
                    break
                data = ser.read(256)
                if not data:
                    continue
                buffer.extend(data)
                while b"\n" in buffer:
                    raw, _, buffer = buffer.partition(b"\n")
                    line = raw.decode("utf-8", errors="replace").strip("\r")
                    if line:
                        self.line_received.emit(line)
            except serial.SerialException as exc:
                self.error.emit(f"Serial read failed: {exc}")
                break
            except OSError as exc:
                self.error.emit(f"Serial disconnected: {exc}")
                break
            time.sleep(0.01)

        if not self._stop_event.is_set():
            self.disconnected.emit()
