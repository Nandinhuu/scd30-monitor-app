from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO

from data_model import CSV_HEADER, SensorSample


class CsvLogger:
    def __init__(self) -> None:
        self._file: TextIO | None = None
        self._writer: csv.writer | None = None
        self.path: Path | None = None

    @property
    def is_logging(self) -> bool:
        return self._file is not None

    def start(self, path: str) -> None:
        self.stop()
        self.path = Path(path)
        file_exists = self.path.exists() and self.path.stat().st_size > 0
        self._file = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if not file_exists:
            self._writer.writerow(CSV_HEADER)
            self._file.flush()

    def write_sample(self, sample: SensorSample) -> None:
        if not self._writer or not self._file:
            return
        self._writer.writerow(sample.to_csv_row())
        self._file.flush()

    def stop(self) -> None:
        if self._file:
            self._file.close()
        self._file = None
        self._writer = None

    def __del__(self) -> None:
        self.stop()
