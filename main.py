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


from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

class FileWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, directories):
        super().__init__()
        self.directories = directories
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)
        self.classifier, self.vectorizer = self.train_classifier()

    def run(self):
        try:
            total_files = sum(len(files) for d in self.directories for _, _, files in os.walk(d))
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
                            self.process_file, file_path, organized_root
                        ))

                    for future in futures:
                        if not self.running:
                            return
                        future.result()
                        processed += 1
                        self.progress.emit(int((processed / total_files) * 100))

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def process_file(self, file_path, organized_root):
        try:
            conn = sqlite3.connect('file_records.db')
            cursor = conn.cursor()
            
            file_stat = os.stat(file_path)
            size_mtime = f"{file_stat.st_size}-{file_stat.st_mtime}"
            
            cursor.execute("SELECT 1 FROM files WHERE size_mtime=?", (size_mtime,))
            if cursor.fetchone():
                conn.close()
                return

            file_hash = self.quick_hash(file_path)
            cursor.execute("SELECT 1 FROM files WHERE hash=?", (file_hash,))
            if cursor.fetchone():
                cursor.execute("INSERT INTO files (hash, path, size_mtime) VALUES (?, ?, ?)",
                              (file_hash, file_path, size_mtime))
                conn.commit()
                conn.close()
                return

            category = self.ai_classify_file(os.path.basename(file_path))
            target_dir = os.path.join(organized_root, category)
            os.makedirs(target_dir, exist_ok=True)

            shutil.move(file_path, os.path.join(target_dir, os.path.basename(file_path)))
            cursor.execute("INSERT INTO files (hash, path, size_mtime) VALUES (?, ?, ?)",
                          (file_hash, os.path.join(target_dir, os.path.basename(file_path)), size_mtime))
            conn.commit()
            conn.close()
        except Exception as e:
            self.error.emit(f"Error processing {file_path}: {str(e)}")

    def quick_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            hasher.update(f.read(1024 * 1024))  # Hash first 1MB for speed
        return hasher.hexdigest()

    def ai_classify_file(self, filename):
        categories = ["Documents", "Images", "Media", "Code", "Archives", "Executables", "Data", "Other"]
        filename_vectorized = self.vectorizer.transform([filename])
        prediction = self.classifier.predict(filename_vectorized)[0]
        return categories[prediction]

    def train_classifier(self):
        categories = ["Documents", "Images", "Media", "Code", "Archives", "Executables", "Data", "Other"]
        training_data = [
            "report.docx", "invoice.pdf", "notes.txt", "presentation.pptx", "spreadsheet.xlsx", "manual.odt",  # Documents
            "photo.jpg", "graphic.png", "wallpaper.jpeg", "illustration.bmp", "vector.svg", "screenshot.tiff",  # Images
            "movie.mp4", "song.mp3", "podcast.wav", "video.mkv", "audio.aac", "clip.flac",  # Media
            "script.py", "index.html", "main.cpp", "program.java", "source.cs", "module.js", "class.ts",  # Code
            "backup.zip", "archive.rar", "compressed.7z", "package.tar", "gzip.gz", "bzipped.bz2",  # Archives
            "installer.exe", "app.dmg", "setup.msi", "binary.bin", "runnable.out", "software.pkg",  # Executables
            "database.db", "data.csv", "config.json", "settings.xml", "metadata.yaml", "spreadsheet.xls",  # Data
            "randomfile.xyz", "misc.unknown", "undefined.tmp"  # Other
        ]
        labels = [0, 0, 0, 0, 0, 0,  # Documents
                  1, 1, 1, 1, 1, 1,  # Images
                  2, 2, 2, 2, 2, 2,  # Media
                  3, 3, 3, 3, 3, 3, 3,  # Code
                  4, 4, 4, 4, 4, 4,  # Archives
                  5, 5, 5, 5, 5, 5,  # Executables
                  6, 6, 6, 6, 6, 6,  # Data
                  7, 7, 7]  # Other
        
        vectorizer = CountVectorizer()
        training_vectors = vectorizer.fit_transform(training_data)
        classifier = MultinomialNB()
        classifier.fit(training_vectors, labels)
        return classifier, vectorizer

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
        menu_container = self.create_menu()  # This returns a QFrame
        content_layout = self.create_content()

        # Add the menu container as a widget
        main_layout.addWidget(menu_container, 1)  # Use addWidget for QFrame
        main_layout.addLayout(content_layout, 4)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Set a futuristic background
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #0d0d1a, stop: 1 #1e1e2f
                );
            }
        """)

    def create_menu(self):
        menu_layout = QVBoxLayout()
        menu_layout.setAlignment(Qt.AlignTop)
        menu_layout.setContentsMargins(20, 40, 20, 40)

        # Increase the spacing between buttons
        menu_layout.setSpacing(20)

        # Create a container for the menu with a distinct background
        menu_container = QFrame()
        menu_container.setStyleSheet("""
            QFrame {
                background-color: #1e1e2f;
                border-radius: 15px;
                border: 2px solid #00ffcc;
            }
        """)
        menu_container.setLayout(menu_layout)

        buttons = [
            ("➕ Add Directories", self.add_directories),
            ("🗑️ Remove Directory", self.remove_selected_directory),
            ("⚙️ Organize Files", self.start_processing),
            ("❌ Cancel", self.cancel_processing),
            ("🚪 Exit", self.close)
        ]

        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(self.button_style())
            btn.clicked.connect(handler)
            btn.setFixedHeight(50)
            menu_layout.addWidget(btn)

        return menu_container

    def create_content(self):
        content_layout = QVBoxLayout()

        # Title with futuristic font
        self.title = QLabel("AI Directory Manager")
        self.title.setStyleSheet("""
            font-size: 28pt;
            font-weight: bold;
            color: #00ffcc;
            font-family: Orbitron, sans-serif;
            margin-bottom: 20px;
        """)
        self.title.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.title)

        # Directory table with futuristic styling
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Selected Directories"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2f;
                color: #00ffcc;
                font-size: 14pt;
                font-family: Orbitron, sans-serif;
                border: 2px solid #00ffcc;
                border-radius: 10px;
            }
            QHeaderView::section {
                background-color: #3a3a5f;
                color: #ffffff;
                font-size: 12pt;
                font-family: Orbitron, sans-serif;
                border: 1px solid #00ffcc;
            }
        """)
        content_layout.addWidget(self.table)

        # Progress bar with futuristic styling
        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e2f;
                border: 2px solid #00ffcc;
                border-radius: 10px;
                text-align: center;
                color: #00ffcc;
                font-family: Orbitron, sans-serif;
            }
            QProgressBar::chunk {
                background-color: #00ffcc;
                border-radius: 10px;
            }
        """)
        content_layout.addWidget(self.progress)

        return content_layout

    def button_style(self):
        return """
            QPushButton {
                font-size: 16pt;
                padding: 13px;
                border-radius: 10px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #2d2d44, stop: 1 #3a3a5f
                );
                color: #00ffcc;
                font-family: Orbitron, sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #3a3a5f, stop: 1 #2d2d44
                );
                color: #ffffff;
                border: 2px solid #ffffff;
            }
            QPushButton:pressed {
                background-color: #00ffcc;
                color: #1e1e2f;
            }
        """

    def add_directories(self):
        if directory := QFileDialog.getExistingDirectory(self, "Select Directory"):
            self.selected_directories.append(directory)
            self.update_directory_table()

    def remove_selected_directory(self):
        selected_row = self.table.currentRow()
        if selected_row == -1:
            self.show_message("Error", "Please select a directory to remove!", QMessageBox.Critical)
            return

        # Remove the selected directory from the list and update the table
        del self.selected_directories[selected_row]
        self.update_directory_table()

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

    def update_directory_table(self):
        # Clear the table
        self.table.setRowCount(0)

        # Populate the table with the selected directories
        for row, directory in enumerate(self.selected_directories):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(directory))

    def closeEvent(self, event):
        self.cancel_processing()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AIDirectoryManager()
    window.show()
    sys.exit(app.exec_())
