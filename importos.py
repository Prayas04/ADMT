import os
import sys
import hashlib
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox, QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPushButton, QDialog, QLineEdit, QLabel, QDialogButtonBox, QFileDialog, QProgressBar, QHBoxLayout
from transformers import pipeline
import pytesseract
from PIL import Image
import json

# File Scanner
def scan_directory(directory_path, extensions=None):
    if not extensions:
        extensions = {".txt", ".jpg", ".png", ".pdf"}  # Default, can be customized
    files_list = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            if Path(file).suffix.lower() in extensions:
                file_path = Path(root) / file
                files_list.append({
                    "name": file,
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "type": file_path.suffix,
                    "tags": None,
                    "hash": compute_file_hash(file_path)
                })
    return files_list

# Compute File Hash for Duplicate Detection
def compute_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

# AI Tagging
def tag_file_content(file_path, custom_categories=None):
    try:
        classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
        file_ext = file_path.suffix.lower()
        content = ""

        if file_ext in [".txt"]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()[:500]
        elif file_ext in [".jpg", ".png", ".jpeg"]:
            content = pytesseract.image_to_string(Image.open(file_path))
        else:
            return "Unsupported"

        if not content.strip():
            return "No content"

        labels = custom_categories if custom_categories else ["Document", "Image", "Music", "Other"]
        result = classifier(content, labels)
        return result["labels"][0]
    except Exception as e:
        print(f"Error tagging {file_path}: {e}")
        return "Error"

# Detect Duplicates
def find_duplicates(files_list):
    hash_dict = {}
    duplicates = []
    for file in files_list:
        file_hash = file["hash"]
        if file_hash in hash_dict:
            duplicates.append((file["path"], hash_dict[file_hash]))
        else:
            hash_dict[file_hash] = file["path"]
    return duplicates

# Settings Dialog
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(400, 200)

        layout = QVBoxLayout()

        # Categories input
        self.cat_label = QLabel("Custom Categories (comma-separated):")
        self.cat_input = QLineEdit()
        self.cat_input.setPlaceholderText("e.g., Invoice, Photo, Music")
        layout.addWidget(self.cat_label)
        layout.addWidget(self.cat_input)

        # File extensions input
        self.ext_label = QLabel("File Extensions to Scan (comma-separated, with dot):")
        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("e.g., .txt, .jpg, .pdf")
        layout.addWidget(self.ext_label)
        layout.addWidget(self.ext_input)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_settings(self):
        categories = [cat.strip() for cat in self.cat_input.text().split(",") if cat.strip()]
        extensions = {ext.strip() for ext in self.ext_input.text().split(",") if ext.strip()}
        return categories, extensions

# Main Application GUI
class DirectoryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Directory Manager")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: #f0f0f0; font-family: Arial; color: #333;")

        # Create main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top buttons
        top_layout = QHBoxLayout()
        self.select_dir_button = QPushButton("Select Directory")
        self.select_dir_button.clicked.connect(self.select_directory)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.show_settings)
        top_layout.addWidget(self.select_dir_button)
        top_layout.addWidget(self.settings_button)
        layout.addLayout(top_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        # Table for files
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Size (KB)", "Type", "Tags", "Path"])
        layout.addWidget(self.table)

        # Load saved settings
        self.custom_categories = ["Document", "Image", "Music", "Other"]
        self.extensions = {".txt", ".jpg", ".png"}
        self.load_settings()

    def load_settings(self):
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
                self.custom_categories = settings.get("categories", self.custom_categories)
                self.extensions = set(settings.get("extensions", list(self.extensions)))
        except FileNotFoundError:
            pass

    def save_settings(self, categories, extensions):
        with open("settings.json", "w") as f:
            json.dump({"categories": categories, "extensions": list(extensions)}, f)

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.custom_categories, self.extensions = dialog.get_settings()
            self.save_settings(self.custom_categories, self.extensions)

    def select_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            self.directory_path = dir_path
            self.scan_and_display()

    def scan_and_display(self):
        if not self.directory_path:
            QMessageBox.warning(self, "Warning", "Please select a directory first.")
            return

        self.progress_bar.setMaximum(100)
        files_list = scan_directory(self.directory_path, self.extensions)

        for i, file in enumerate(files_list):
            file["tags"] = tag_file_content(Path(file["path"]), self.custom_categories)
            self.progress_bar.setValue((i + 1) / len(files_list) * 100)

        duplicates = find_duplicates(files_list)
        if duplicates:
            print("Duplicates found:", duplicates)

        self.table.setRowCount(len(files_list))
        for row, file in enumerate(files_list):
            self.table.setItem(row, 0, QTableWidgetItem(file["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(str(file["size"] // 1024)))
            self.table.setItem(row, 2, QTableWidgetItem(file["type"]))
            self.table.setItem(row, 3, QTableWidgetItem(file["tags"] or "N/A"))
            self.table.setItem(row, 4, QTableWidgetItem(file["path"]))

        self.table.resizeColumnsToContents()

# Entry Point
if __name__ == "__main__":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # Update for your system
    app = QApplication(sys.argv)
    window = DirectoryApp()
    window.show()
    sys.exit(app.exec_())