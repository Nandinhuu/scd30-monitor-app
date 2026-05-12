from __future__ import annotations

import sys
from collections import deque
from datetime import datetime

import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ble_worker import BLEDataSource, BleDeviceInfo, BleScanner
from csv_logger import CsvLogger
from data_model import SensorSample, is_status_line, parse_sensor_line
from data_source import DataSource
from serial_worker import SerialDataSource, available_serial_ports


MAX_VISIBLE_SAMPLES = 1000


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("B-U585I-IOT02A SCD30 Data Monitor")
        self.resize(1280, 820)

        self.data_source: DataSource | None = None
        self.csv_logger = CsvLogger()
        self.ble_scanner = BleScanner()
        self.ble_devices: list[BleDeviceInfo] = []
        self.target_samples: int | None = None

        self.sample_numbers: deque[int] = deque(maxlen=MAX_VISIBLE_SAMPLES)
        self.co2_values: deque[float] = deque(maxlen=MAX_VISIBLE_SAMPLES)
        self.temperature_values: deque[float] = deque(maxlen=MAX_VISIBLE_SAMPLES)
        self.humidity_values: deque[float] = deque(maxlen=MAX_VISIBLE_SAMPLES)
        self.uv_values: deque[float] = deque(maxlen=MAX_VISIBLE_SAMPLES)

        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(2000)
        self.heartbeat_timer.timeout.connect(lambda: self.send_command("HEARTBEAT"))

        self._build_ui()
        self._connect_signals()
        self.refresh_ports()
        self.log("Ready. Connect over Serial or BLE, then press Start Collection.")

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)

        left = QVBoxLayout()
        left.addWidget(self._build_connection_group())
        left.addWidget(self._build_control_group())
        left.addWidget(self._build_csv_group())
        left.addStretch()

        right = QVBoxLayout()
        right.addWidget(self._build_live_display_group())
        right.addWidget(self._build_chart_group(), stretch=1)
        right.addWidget(self._build_log_group(), stretch=1)

        root.addLayout(left, stretch=0)
        root.addLayout(right, stretch=1)
        self.setCentralWidget(central)

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Connection")
        layout = QVBoxLayout(group)

        self.connection_tabs = QTabWidget()

        serial_page = QWidget()
        serial_form = QFormLayout(serial_page)
        self.port_combo = QComboBox()
        self.refresh_ports_button = QPushButton("Refresh COM Ports")
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud_combo.setCurrentText("115200")
        serial_form.addRow("COM Port", self.port_combo)
        serial_form.addRow("Baud Rate", self.baud_combo)
        serial_form.addRow("", self.refresh_ports_button)

        ble_page = QWidget()
        ble_form = QFormLayout(ble_page)
        self.ble_device_combo = QComboBox()
        self.ble_scan_button = QPushButton("Scan BLE Devices")
        self.ble_notify_uuid = QLineEdit()
        self.ble_write_uuid = QLineEdit()
        self.ble_notify_uuid.setPlaceholderText("Notify characteristic UUID from ST BLE example")
        self.ble_write_uuid.setPlaceholderText("Write characteristic UUID from ST BLE example")
        ble_form.addRow("BLE Device", self.ble_device_combo)
        ble_form.addRow("", self.ble_scan_button)
        ble_form.addRow("Notify UUID", self.ble_notify_uuid)
        ble_form.addRow("Write UUID", self.ble_write_uuid)

        self.connection_tabs.addTab(serial_page, "Serial / ST-LINK VCP")
        self.connection_tabs.addTab(ble_page, "BLE")

        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.connection_status = QLabel("Disconnected")
        self.connection_status.setObjectName("ConnectionStatus")

        buttons = QHBoxLayout()
        buttons.addWidget(self.connect_button)
        buttons.addWidget(self.disconnect_button)

        layout.addWidget(self.connection_tabs)
        layout.addLayout(buttons)
        layout.addWidget(self.connection_status)
        return group

    def _build_control_group(self) -> QGroupBox:
        group = QGroupBox("Control")
        layout = QGridLayout(group)

        self.sync_time_button = QPushButton("Sync Time")
        self.start_button = QPushButton("Start Collection")
        self.stop_button = QPushButton("Stop Collection")
        self.reset_button = QPushButton("Reset")
        self.get_status_button = QPushButton("Get Status")

        self.interval_input = QSpinBox()
        self.interval_input.setRange(100, 3_600_000)
        self.interval_input.setValue(2000)
        self.interval_input.setSuffix(" ms")
        self.set_interval_button = QPushButton("Set Interval")

        self.target_input = QSpinBox()
        self.target_input.setRange(0, 1_000_000)
        self.target_input.setValue(100)
        self.target_input.setSpecialValueText("No target")
        self.set_target_button = QPushButton("Set Target Samples")

        layout.addWidget(self.sync_time_button, 0, 0)
        layout.addWidget(self.start_button, 0, 1)
        layout.addWidget(self.stop_button, 1, 0)
        layout.addWidget(self.reset_button, 1, 1)
        layout.addWidget(self.get_status_button, 2, 0, 1, 2)
        layout.addWidget(QLabel("Sampling Interval"), 3, 0)
        layout.addWidget(self.interval_input, 3, 1)
        layout.addWidget(self.set_interval_button, 4, 0, 1, 2)
        layout.addWidget(QLabel("Target Samples"), 5, 0)
        layout.addWidget(self.target_input, 5, 1)
        layout.addWidget(self.set_target_button, 6, 0, 1, 2)
        return group

    def _build_csv_group(self) -> QGroupBox:
        group = QGroupBox("CSV Logging")
        layout = QVBoxLayout(group)
        self.csv_path_input = QLineEdit()
        self.csv_path_input.setPlaceholderText("Choose output CSV file")
        self.choose_csv_button = QPushButton("Choose CSV File")
        self.start_csv_button = QPushButton("Start CSV Logging")
        self.stop_csv_button = QPushButton("Stop CSV Logging")
        self.stop_csv_button.setEnabled(False)
        self.csv_status = QLabel("CSV logging stopped")

        layout.addWidget(self.csv_path_input)
        layout.addWidget(self.choose_csv_button)
        layout.addWidget(self.start_csv_button)
        layout.addWidget(self.stop_csv_button)
        layout.addWidget(self.csv_status)
        return group

    def _build_live_display_group(self) -> QGroupBox:
        group = QGroupBox("Latest Data")
        layout = QGridLayout(group)
        self.time_value = QLabel("--")
        self.sample_value = QLabel("[0/∞]")
        self.uv_value = QLabel("--")
        self.co2_value = QLabel("--")
        self.temperature_value = QLabel("--")
        self.humidity_value = QLabel("--")

        labels = [
            ("Time", self.time_value),
            ("Sample", self.sample_value),
            ("UV Level", self.uv_value),
            ("CO2 Concentration", self.co2_value),
            ("Temperature", self.temperature_value),
            ("Humidity", self.humidity_value),
        ]
        for row, (name, value_label) in enumerate(labels):
            layout.addWidget(QLabel(name + ":"), row, 0)
            layout.addWidget(value_label, row, 1)
        return group

    def _build_chart_group(self) -> QGroupBox:
        group = QGroupBox("Real-Time Chart")
        layout = QVBoxLayout(group)
        toggles = QHBoxLayout()
        self.co2_checkbox = QCheckBox("CO2")
        self.temp_checkbox = QCheckBox("Temperature")
        self.humidity_checkbox = QCheckBox("Humidity")
        self.uv_checkbox = QCheckBox("UV")
        for checkbox in [self.co2_checkbox, self.temp_checkbox, self.humidity_checkbox, self.uv_checkbox]:
            checkbox.setChecked(True)
            toggles.addWidget(checkbox)
        toggles.addStretch()

        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.addLegend()
        self.plot.setLabel("bottom", "Sample Index")
        self.plot.setLabel("left", "Sensor Value")
        self.co2_curve = self.plot.plot(pen=pg.mkPen("#1f77b4", width=2), name="CO2 ppm")
        self.temp_curve = self.plot.plot(pen=pg.mkPen("#d62728", width=2), name="Temperature C")
        self.humidity_curve = self.plot.plot(pen=pg.mkPen("#2ca02c", width=2), name="Humidity RH")
        self.uv_curve = self.plot.plot(pen=pg.mkPen("#9467bd", width=2), name="UV Level")

        layout.addLayout(toggles)
        layout.addWidget(self.plot)
        return group

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("Log")
        layout = QVBoxLayout(group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(2000)
        layout.addWidget(self.log_output)
        return group

    def _connect_signals(self) -> None:
        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.ble_scan_button.clicked.connect(self.scan_ble)
        self.ble_scanner.scan_finished.connect(self.on_ble_scan_finished)
        self.ble_scanner.error.connect(self.log_error)
        self.connect_button.clicked.connect(self.connect_data_source)
        self.disconnect_button.clicked.connect(self.disconnect_data_source)
        self.sync_time_button.clicked.connect(self.sync_time)
        self.start_button.clicked.connect(lambda: self.send_command("START"))
        self.stop_button.clicked.connect(lambda: self.send_command("STOP"))
        self.reset_button.clicked.connect(self.reset_board)
        self.get_status_button.clicked.connect(lambda: self.send_command("GET_STATUS"))
        self.set_interval_button.clicked.connect(self.set_interval)
        self.set_target_button.clicked.connect(self.set_target_samples)
        self.choose_csv_button.clicked.connect(self.choose_csv_path)
        self.start_csv_button.clicked.connect(self.start_csv_logging)
        self.stop_csv_button.clicked.connect(self.stop_csv_logging)

        for checkbox in [self.co2_checkbox, self.temp_checkbox, self.humidity_checkbox, self.uv_checkbox]:
            checkbox.toggled.connect(self.update_chart_visibility)

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = available_serial_ports()
        self.port_combo.addItems(ports)
        if current in ports:
            self.port_combo.setCurrentText(current)
        self.log(f"Found {len(ports)} serial port(s).")

    def scan_ble(self) -> None:
        self.ble_scan_button.setEnabled(False)
        self.log("Scanning BLE devices...")
        self.ble_scanner.scan()

    def on_ble_scan_finished(self, devices: list[BleDeviceInfo]) -> None:
        self.ble_devices = devices
        self.ble_device_combo.clear()
        for device in devices:
            self.ble_device_combo.addItem(f"{device.name} ({device.address})", device.address)
        self.ble_scan_button.setEnabled(True)
        self.log(f"Found {len(devices)} BLE device(s).")

    def connect_data_source(self) -> None:
        if self.data_source and self.data_source.is_connected():
            self.log_error("Already connected")
            return

        if self.connection_tabs.currentIndex() == 0:
            port = self.port_combo.currentText()
            if not port:
                self.log_error("Select a COM port first")
                return
            self.data_source = SerialDataSource(port, int(self.baud_combo.currentText()))
        else:
            address = self.ble_device_combo.currentData()
            notify_uuid = self.ble_notify_uuid.text().strip()
            write_uuid = self.ble_write_uuid.text().strip()
            if not address:
                self.log_error("Scan and select a BLE device first")
                return
            if not notify_uuid or not write_uuid:
                self.log_error("Enter BLE notify and write characteristic UUIDs")
                return
            self.data_source = BLEDataSource(address, notify_uuid, write_uuid)

        self.data_source.connected.connect(self.on_connected)
        self.data_source.disconnected.connect(self.on_disconnected)
        self.data_source.line_received.connect(self.on_line_received)
        self.data_source.log_message.connect(self.log)
        self.data_source.error.connect(self.log_error)
        self.connection_status.setText("Connecting...")
        self.data_source.connect_source()

    def disconnect_data_source(self) -> None:
        if not self.data_source:
            return
        if self.data_source.is_connected():
            self.send_command("APP_DISCONNECT")
        self.heartbeat_timer.stop()
        self.data_source.disconnect_source()

    def on_connected(self) -> None:
        self.connection_status.setText("Connected")
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.send_command("APP_HELLO")
        self.heartbeat_timer.start()

    def on_disconnected(self) -> None:
        self.connection_status.setText("Disconnected")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.heartbeat_timer.stop()

    def send_command(self, command: str) -> None:
        if not self.data_source or not self.data_source.is_connected():
            self.log_error(f"Cannot send {command}: not connected")
            return
        self.data_source.send_line(command)

    def sync_time(self) -> None:
        self.send_command("SYNC_TIME:" + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def set_interval(self) -> None:
        self.send_command(f"SET_INTERVAL:{self.interval_input.value()}")

    def set_target_samples(self) -> None:
        value = self.target_input.value()
        self.target_samples = value if value > 0 else None
        if value > 0:
            self.send_command(f"SET_TARGET_SAMPLES:{value}")
        else:
            self.log("Target samples cleared locally. Board target unchanged until firmware supports clear command.")
        self.update_sample_label()

    def reset_board(self) -> None:
        self.send_command("RESET")
        self.clear_local_data()

    def clear_local_data(self) -> None:
        self.sample_numbers.clear()
        self.co2_values.clear()
        self.temperature_values.clear()
        self.humidity_values.clear()
        self.uv_values.clear()
        self.time_value.setText("--")
        self.sample_value.setText("[0/∞]" if self.target_samples is None else f"[0/{self.target_samples}]")
        self.uv_value.setText("--")
        self.co2_value.setText("--")
        self.temperature_value.setText("--")
        self.humidity_value.setText("--")
        self.update_chart()

    def choose_csv_path(self) -> None:
        default_name = "scd30_log.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Choose CSV Output", default_name, "CSV Files (*.csv)")
        if path:
            self.csv_path_input.setText(path)

    def start_csv_logging(self) -> None:
        path = self.csv_path_input.text().strip()
        if not path:
            self.log_error("Choose a CSV file path first")
            return
        try:
            self.csv_logger.start(path)
        except OSError as exc:
            self.log_error(f"CSV logging failed: {exc}")
            return
        self.csv_status.setText(f"Logging to {path}")
        self.start_csv_button.setEnabled(False)
        self.stop_csv_button.setEnabled(True)
        self.log(f"CSV logging started: {path}")

    def stop_csv_logging(self) -> None:
        self.csv_logger.stop()
        self.csv_status.setText("CSV logging stopped")
        self.start_csv_button.setEnabled(True)
        self.stop_csv_button.setEnabled(False)
        self.log("CSV logging stopped")

    def on_line_received(self, line: str) -> None:
        self.log(f"< {line}")
        if is_status_line(line):
            if line.startswith("ERROR:"):
                self.log_error(line)
            return

        try:
            sample = parse_sensor_line(line)
        except ValueError as exc:
            self.log_error(f"Parse error: {exc}; raw={line}")
            return

        self.add_sample(sample)
        if self.csv_logger.is_logging:
            self.csv_logger.write_sample(sample)

    def add_sample(self, sample: SensorSample) -> None:
        self.sample_numbers.append(sample.sample_index)
        self.co2_values.append(sample.co2_ppm)
        self.temperature_values.append(sample.temperature_c)
        self.humidity_values.append(sample.humidity_rh)
        self.uv_values.append(sample.uv_level)

        self.time_value.setText(sample.timestamp)
        self.update_sample_label(sample.sample_index)
        self.uv_value.setText(f"{sample.uv_level:.2f}")
        self.co2_value.setText(f"{sample.co2_ppm:.2f} ppm")
        self.temperature_value.setText(f"{sample.temperature_c:.2f} °C")
        self.humidity_value.setText(f"{sample.humidity_rh:.2f} %RH")
        self.update_chart()

    def update_sample_label(self, current: int | None = None) -> None:
        if current is None:
            current = self.sample_numbers[-1] if self.sample_numbers else 0
        target = "∞" if self.target_samples is None else str(self.target_samples)
        self.sample_value.setText(f"[{current}/{target}]")

    def update_chart(self) -> None:
        x = list(self.sample_numbers)
        self.co2_curve.setData(x, list(self.co2_values))
        self.temp_curve.setData(x, list(self.temperature_values))
        self.humidity_curve.setData(x, list(self.humidity_values))
        self.uv_curve.setData(x, list(self.uv_values))
        self.update_chart_visibility()

    def update_chart_visibility(self) -> None:
        self.co2_curve.setVisible(self.co2_checkbox.isChecked())
        self.temp_curve.setVisible(self.temp_checkbox.isChecked())
        self.humidity_curve.setVisible(self.humidity_checkbox.isChecked())
        self.uv_curve.setVisible(self.uv_checkbox.isChecked())

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{stamp}] {message}")

    def log_error(self, message: str) -> None:
        self.log(f"ERROR: {message}")

    def closeEvent(self, event) -> None:
        if self.data_source and self.data_source.is_connected():
            self.send_command("APP_DISCONNECT")
            self.data_source.disconnect_source()
        self.csv_logger.stop()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(
        """
        QMainWindow { background: #f7f8fa; }
        QGroupBox {
            font-weight: 600;
            border: 1px solid #c9ced6;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QPushButton { min-height: 28px; }
        QLabel#ConnectionStatus { font-weight: 600; }
        """
    )
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
