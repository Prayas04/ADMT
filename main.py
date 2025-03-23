import sys
import os
import shutil
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (QApplication, QFileDialog, QMainWindow, QPushButton, 
                            QLabel, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, 
                            QFrame, QGraphicsOpacityEffect, QTableWidget, QTableWidgetItem, 
                            QMessageBox, QProgressBar)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QSize, QPropertyAnimation, QThread, pyqtSignal
from qdarkstyle import load_stylesheet

class FileWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, directories):
        super().__init__()
        self.directories = directories
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)

    def run(self):
        try:
            conn = sqlite3.connect('file_records.db', check_same_thread=False)
            cursor = conn.cursor()
            total_files = sum(len(files) for _, _, files in (os.walk(d) for d in self.directories))
            processed = 0

            for directory in self.directories:
                organized_root = os.path.join(directory, "Organized")
                os.makedirs(organized_root, exist_ok=True)

                for root, dirs, files in os.walk(directory):
                    if not self.running:
                        return
                    if "Organized" in dirs:
                        dirs.remove("Organized")

                    futures = []
                    for file in files:
                        file_path = os.path.join(root, file)
                        futures.append(self.executor.submit(
                            self.process_file, file_path, organized_root, cursor
                        ))

                    for future in futures:
                        if not self.running:
                            return
                        future.result()
                        processed += 1
                        self.progress.emit(int((processed / total_files) * 100))

            conn.commit()
            conn.close()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def process_file(self, file_path, organized_root, cursor):
        try:
            file_stat = os.stat(file_path)
            size_mtime = f"{file_stat.st_size}-{file_stat.st_mtime}"
            
            cursor.execute("SELECT 1 FROM files WHERE size_mtime=?", (size_mtime,))
            if cursor.fetchone():
                return

            file_hash = self.quick_hash(file_path)
            cursor.execute("SELECT 1 FROM files WHERE hash=?", (file_hash,))
            if cursor.fetchone():
                cursor.execute("INSERT INTO files (hash, path, size_mtime) VALUES (?, ?, ?)",
                              (file_hash, file_path, size_mtime))
                return

            category = self.classify_file(os.path.basename(file_path))
            target_dir = os.path.join(organized_root, category)
            os.makedirs(target_dir, exist_ok=True)

            shutil.move(file_path, os.path.join(target_dir, os.path.basename(file_path)))
            cursor.execute("INSERT INTO files (hash, path, size_mtime) VALUES (?, ?, ?)",
                          (file_hash, os.path.join(target_dir, os.path.basename(file_path)), size_mtime))
        except Exception as e:
            self.error.emit(f"Error processing {file_path}: {str(e)}")

    def quick_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            hasher.update(f.read(1024 * 1024))  # Hash first 1MB for speed
        return hasher.hexdigest()

    def classify_file(self, filename):
        ext = os.path.splitext(filename)[1][1:].lower()
        categories = {
            'Documents': {'doc', 'docx', 'pdf', 'txt', 'rtf', 'odt', 'xls', 'xlsx', 'ppt', 'pptx'},
            'Images': {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'tiff'},
            'Media': {'mp4', 'mov', 'avi', 'mkv', 'mp3', 'wav', 'flac', 'aac', 'wma'},
            'Code': {'py', 'js', 'html', 'css', 'java', 'cpp', 'c', 'h', 'php', 'rb'},
            'Archives': {'zip', 'rar', 'tar', 'gz', '7z', 'bz2'},
            'Executables': {'exe', 'dmg', 'app', 'msi', 'deb'},
            'Data': {'csv', 'json', 'xml', 'db', 'sql', 'dat'}
        }
        
        for category, exts in categories.items():
            if ext in exts:
                return category
        
        return 'Other'

    def stop(self):
        self.running = False
        self.executor.shutdown(wait=False)

class AIDirectoryManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Powered Directory Manager")
        self.setMinimumSize(1280, 720)
        self.setStyleSheet(load_stylesheet())
        self.selected_directories = []
        self.worker = None
        self.init_db()
        self.init_ui()

    def init_db(self):
        conn = sqlite3.connect('file_records.db')
        cursor = conn.cursor()

        # Drop the existing table if it doesn't have the correct schema
        cursor.execute("PRAGMA table_info(files)")
        columns = [col[1] for col in cursor.fetchall()]
        if "size_mtime" not in columns:
            cursor.execute("DROP TABLE IF EXISTS files")

        # Create the table with the correct schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                hash TEXT,
                path TEXT UNIQUE,
                size_mtime TEXT,
                UNIQUE(hash, size_mtime)
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hash ON files (hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_size_mtime ON files (size_mtime)")
        conn.commit()
        conn.close()

    def init_ui(self):
        main_layout = QHBoxLayout()
        menu_layout = self.create_menu()
        content_layout = self.create_content()
        main_layout.addLayout(menu_layout, 1)
        main_layout.addLayout(content_layout, 4)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def create_menu(self):
        menu_layout = QVBoxLayout()
        menu_layout.setAlignment(Qt.AlignTop)
        menu_layout.setContentsMargins(20, 40, 20, 40)

        buttons = [
            ("Add Directories", self.add_directories),
            ("Organize Files", self.start_processing),
            ("Cancel", self.cancel_processing),
            ("Exit", self.close)
        ]

        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(self.button_style())
            btn.clicked.connect(handler)
            btn.setFixedHeight(50)
            menu_layout.addWidget(btn)

        return menu_layout

    def create_content(self):
        content_layout = QVBoxLayout()
        self.title = QLabel("AI Directory Organizer")
        self.title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        content_layout.addWidget(self.title)

        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Selected Directories"])
        self.table.horizontalHeader().setStretchLastSection(True)
        content_layout.addWidget(self.table)

        self.progress = QProgressBar()
        self.progress.setStyleSheet("QProgressBar { height: 25px; }")
        content_layout.addWidget(self.progress)

        return content_layout

    def button_style(self):
        return """
            QPushButton {
                font-size: 14pt;
                padding: 10px;
                border-radius: 5px;
                background: #444;
            }
            QPushButton:hover {
                background: #666;
            }
        """

    def add_directories(self):
        if directory := QFileDialog.getExistingDirectory(self, "Select Directory"):
            self.selected_directories.append(directory)
            self.table.setRowCount(len(self.selected_directories))
            for row, dir in enumerate(self.selected_directories):
                self.table.setItem(row, 0, QTableWidgetItem(dir))

    def start_processing(self):
        if not self.selected_directories:
            self.show_message("Error", "Please select directories first!", QMessageBox.Critical)
            return

        self.worker = FileWorker(self.selected_directories)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.show_error)
        self.worker.start()

    def cancel_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self.progress.setValue(0)
            self.show_message("Cancelled", "Operation cancelled successfully", QMessageBox.Information)

    def on_finished(self):
        self.progress.setValue(0)
        self.show_message("Success", "Files organized successfully!", QMessageBox.Information)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def show_message(self, title, message, icon):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(icon)
        msg.show()

    def closeEvent(self, event):
        self.cancel_processing()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AIDirectoryManager()
    window.show()
    sys.exit(app.exec_())
