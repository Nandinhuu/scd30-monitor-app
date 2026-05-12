from __future__ import annotations

from dataclasses import dataclass


CSV_HEADER = [
    "timestamp",
    "sample_index",
    "co2_ppm",
    "temperature_c",
    "humidity_rh",
    "uv_level",
]


@dataclass(frozen=True)
class SensorSample:
    timestamp: str
    sample_index: int
    co2_ppm: float
    temperature_c: float
    humidity_rh: float
    uv_level: float = 0.0

    def to_csv_row(self) -> list[str]:
        return [
            self.timestamp,
            str(self.sample_index),
            f"{self.co2_ppm:.2f}",
            f"{self.temperature_c:.2f}",
            f"{self.humidity_rh:.2f}",
            f"{self.uv_level:.2f}",
        ]


def parse_sensor_line(line: str) -> SensorSample:
    """Parse one CSV data line from the board.

    Expected format:
    timestamp,sample_index,co2_ppm,temperature_c,humidity_rh,uv_level

    The uv_level field is optional for the first hardware revision and defaults
    to 0.00 when omitted.
    """
    text = line.strip()
    if not text:
        raise ValueError("empty line")

    parts = [part.strip() for part in text.split(",")]
    if len(parts) < 5:
        raise ValueError("expected at least 5 CSV fields")

    timestamp = parts[0]
    if not timestamp:
        raise ValueError("missing timestamp")

    try:
        sample_index = int(parts[1])
        co2_ppm = float(parts[2])
        temperature_c = float(parts[3])
        humidity_rh = float(parts[4])
        uv_level = float(parts[5]) if len(parts) >= 6 and parts[5] else 0.0
    except ValueError as exc:
        raise ValueError(f"invalid numeric value: {exc}") from exc

    return SensorSample(
        timestamp=timestamp,
        sample_index=sample_index,
        co2_ppm=co2_ppm,
        temperature_c=temperature_c,
        humidity_rh=humidity_rh,
        uv_level=uv_level,
    )


def is_status_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    exact_statuses = {
        "TIME_SYNC_OK",
        "DATA_COLLECTION_START",
        "DATA_COLLECTION_STOP",
        "RESET_OK",
        "INTERVAL_SET_OK",
        "TARGET_SAMPLES_SET_OK",
        "APP_CONNECTED_OK",
        "HEARTBEAT_OK",
    }
    return text in exact_statuses or text.startswith("STATUS:") or text.startswith("ERROR:")
