import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QListWidget, QTableWidget, QTableWidgetItem, 
    QLabel, QFileDialog, QComboBox, QProgressBar, QTextEdit,
    QSplitter, QHeaderView, QGroupBox, QStatusBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QColor, QFont, QAction

from toolkit import AstroPreprocessor

class WorkerThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int)

    def __init__(self, processor, file_paths, out_dir, image_type, debayer_algo):
        super().__init__()
        self.processor = processor
        self.file_paths = file_paths
        self.out_dir = out_dir
        self.image_type = image_type
        self.debayer_algo = debayer_algo

    def run(self):
        count = self.processor.batch_convert(
            self.file_paths, 
            self.out_dir, 
            self.image_type, 
            self.debayer_algo,
            lambda i, total, name: self.progress.emit(i, total, name)
        )
        self.finished.emit(count)

class ImageCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='#1e1e1e')
        self.axes = self.fig.add_subplot(111)
        self.axes.set_facecolor('#1e1e1e')
        self.axes.axis('off')
        super().__init__(self.fig)
        self.setParent(parent)

    def display_image(self, data):
        self.axes.clear()
        self.axes.axis('off')
        
        if data is None:
            self.draw()
            return

        # Simple auto-stretch (median + 3*std dev)
        # This is common in astro-processing to make dark images visible
        if data.ndim == 3:
            # RGB (C, H, W)
            display_data = np.transpose(data, (1, 2, 0))
        else:
            display_data = data

        # Normalize for display
        vmin = np.percentile(display_data, 1)
        vmax = np.percentile(display_data, 99)
        
        self.axes.imshow(display_data, vmin=vmin, vmax=vmax, cmap='gray' if data.ndim == 2 else None)
        self.fig.tight_layout(pad=0)
        self.draw()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAW/FITS Preprocessing Toolkit")
        self.setMinimumSize(1200, 800)
        
        self.processor = AstroPreprocessor()
        self.files_to_process = []
        
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Splitter for Queue, Preview, and Inspector
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. Left Panel: File Queue
        left_panel = QGroupBox("File Queue")
        left_layout = QVBoxLayout(left_panel)
        
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.load_selected_preview)
        left_layout.addWidget(self.file_list)
        
        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_queue)
        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_clear)
        left_layout.addLayout(btn_layout)
        
        # 2. Middle Panel: Preview
        mid_panel = QGroupBox("Image Preview")
        mid_layout = QVBoxLayout(mid_panel)
        self.canvas = ImageCanvas(self)
        mid_layout.addWidget(self.canvas)
        
        # 3. Right Panel: Inspector & Log
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Header Info Table
        self.header_table = QTableWidget(0, 3)
        self.header_table.setHorizontalHeaderLabels(["Key", "Value", "Comment"])
        self.header_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_splitter.addWidget(self.header_table)
        
        # Log Output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Processing logs will appear here...")
        right_splitter.addWidget(self.log_output)
        
        top_splitter.addWidget(left_panel)
        top_splitter.addWidget(mid_panel)
        top_splitter.addWidget(right_splitter)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 4)
        top_splitter.setStretchFactor(2, 2)
        
        main_layout.addWidget(top_splitter)
        
        # Bottom Panel: Controls
        controls_group = QGroupBox("Processing Settings")
        controls_layout = QHBoxLayout(controls_group)
        
        controls_layout.addWidget(QLabel("Algorithm:"))
        self.combo_algo = QComboBox()
        self.combo_algo.addItems(["AHD", "Bilinear", "VNG", "PPG"])
        controls_layout.addWidget(self.combo_algo)
        
        controls_layout.addWidget(QLabel("Type:"))
        self.combo_type = QComboBox()
        self.combo_type.addItems(["LIGHT", "DARK", "FLAT", "BIAS"])
        controls_layout.addWidget(self.combo_type)
        
        self.btn_output_dir = QPushButton("Select Output Folder...")
        self.btn_output_dir.clicked.connect(self.select_output_dir)
        controls_layout.addWidget(self.btn_output_dir)
        
        self.lbl_output = QLabel("output/")
        controls_layout.addWidget(self.lbl_output)
        
        controls_layout.addStretch()
        
        self.btn_process = QPushButton("START PROCESSING")
        self.btn_process.clicked.connect(self.start_processing)
        self.btn_process.setMinimumHeight(40)
        self.btn_process.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        controls_layout.addWidget(self.btn_process)
        
        main_layout.addWidget(controls_group)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        self.setStatusBar(QStatusBar())

    def apply_styles(self):
        dark_qss = """
        QMainWindow, QWidget {
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Segoe UI', sans-serif;
        }
        QGroupBox {
            border: 1px solid #3c3c3c;
            margin-top: 10px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }
        QPushButton {
            background-color: #333333;
            border: 1px solid #454545;
            padding: 5px 15px;
            border-radius: 2px;
        }
        QPushButton:hover {
            background-color: #454545;
        }
        QListWidget, QTableWidget, QTextEdit {
            background-color: #252526;
            border: 1px solid #3c3c3c;
            color: #cccccc;
        }
        QHeaderView::section {
            background-color: #2d2d2d;
            border: 1px solid #3c3c3c;
            padding: 4px;
        }
        QProgressBar {
            border: 1px solid #3c3c3c;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #0658ad;
        }
        """
        self.setStyleSheet(dark_qss)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "", 
            "All Images (*.cr2 *.nef *.arw *.dng *.fits *.fit *.fts);;RAW Files (*.cr2 *.nef *.arw *.dng);;FITS Files (*.fits *.fit *.fts)"
        )
        if files:
            for f in files:
                if f not in self.files_to_process:
                    self.files_to_process.append(f)
                    self.file_list.addItem(os.path.basename(f))

    def clear_queue(self):
        self.files_to_process = []
        self.file_list.clear()
        self.header_table.setRowCount(0)
        self.canvas.display_image(None)

    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.processor.output_dir = dir_path
            self.lbl_output.setText(os.path.basename(dir_path) if dir_path else "output/")

    def load_selected_preview(self, item):
        idx = self.file_list.row(item)
        file_path = self.files_to_process[idx]
        ext = os.path.splitext(file_path)[1].lower()
        
        self.log_output.append(f"Previewing: {os.path.basename(file_path)}")
        
        try:
            if ext in ('.fits', '.fit', '.fts'):
                data, header = self.processor.load_fits(file_path)
                self.canvas.display_image(data)
                self.update_header_table(header)
            else:
                # RAW preview is slow, so we just show a placeholder or debayer quickly
                # For this tool, we'll actually debayer it since it's desktop
                data = self.processor.read_raw_linear(file_path, self.combo_algo.currentText())
                self.canvas.display_image(data)
                info = self.processor.get_raw_info(file_path)
                self.update_info_table(info)
        except Exception as e:
            self.log_output.append(f"Error loading preview: {e}")

    def update_header_table(self, header):
        if not header:
            self.header_table.setRowCount(0)
            return
            
        self.header_table.setRowCount(len(header))
        for i, key in enumerate(header.keys()):
            val = str(header[key])
            comment = header.comments[key] if key in header.comments else ""
            self.header_table.setItem(i, 0, QTableWidgetItem(key))
            self.header_table.setItem(i, 1, QTableWidgetItem(val))
            self.header_table.setItem(i, 2, QTableWidgetItem(comment))

    def update_info_table(self, info):
        self.header_table.setRowCount(len(info))
        for i, (k, v) in enumerate(info.items()):
            self.header_table.setItem(i, 0, QTableWidgetItem(k))
            self.header_table.setItem(i, 1, QTableWidgetItem(str(v)))
            self.header_table.setItem(i, 2, QTableWidgetItem(""))

    def start_processing(self):
        if not self.files_to_process:
            self.log_output.append("No files in queue!")
            return
            
        self.btn_process.setEnabled(False)
        self.btn_add_files.setEnabled(False)
        self.btn_clear.setEnabled(False)
        
        self.log_output.append("--- Starting Batch Job ---")
        
        self.worker = WorkerThread(
            self.processor, 
            self.files_to_process, 
            self.processor.output_dir,
            self.combo_type.currentText(),
            self.combo_algo.currentText()
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, i, total, filename):
        val = int((i / total) * 100)
        self.progress_bar.setValue(val)
        self.log_output.append(f"Processing ({i+1}/{total}): {filename}")

    def on_finished(self, count):
        self.progress_bar.setValue(100)
        self.log_output.append(f"--- Job Finished! {count} files processed. ---")
        self.btn_process.setEnabled(True)
        self.btn_add_files.setEnabled(True)
        self.btn_clear.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
