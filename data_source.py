from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class DataSource(QObject):
    connected = Signal()
    disconnected = Signal()
    line_received = Signal(str)
    log_message = Signal(str)
    error = Signal(str)

    def connect_source(self) -> None:
        raise NotImplementedError

    def disconnect_source(self) -> None:
        raise NotImplementedError

    def send_line(self, line: str) -> None:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError
