import sys
import os
import shutil
import hashlib
import sqlite3
import spacy
from PyQt5.QtWidgets import QApplication, QFileDialog, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QSize
from qdarkstyle import load_stylesheet

class AIDirectoryManager:
    def __init__(self, base_path):
        self.base_path = base_path
        self.db_path = os.path.join(base_path, "file_metadata.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.nlp = spacy.load("en_core_web_sm")
        self._initialize_db()

    def _initialize_db(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS files (
                                id INTEGER PRIMARY KEY,
                                filename TEXT,
                                filepath TEXT,
                                hash TEXT,
                                category TEXT)''')
        self.conn.commit()

    def compute_file_hash(self, filepath):
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def create_backup(self):
        if not os.path.exists(self.backup_path):
            os.makedirs(self.backup_path)
        for root, _, files in os.walk(self.base_path):
            for file in files:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, self.base_path)
                backup_filepath = os.path.join(self.backup_path, rel_path)
                os.makedirs(os.path.dirname(backup_filepath), exist_ok=True)
                shutil.copy2(filepath, backup_filepath)

    def scan_directory(self):
        for root, _, files in os.walk(self.base_path):
            for file in files:
                filepath = os.path.join(root, file)
                file_hash = self.compute_file_hash(filepath)
                self.cursor.execute("SELECT * FROM files WHERE hash=?", (file_hash,))
                if not self.cursor.fetchone():
                    category = self.classify_file(file)
                    self.cursor.execute("INSERT INTO files (filename, filepath, hash, category) VALUES (?, ?, ?, ?)",
                                        (file, filepath, file_hash, category))
                    self.conn.commit()

    def classify_file(self, filename):
        doc = self.nlp(filename)
        if any(token.text.lower() in ["invoice", "receipt", "bill"] for token in doc):
            return "Financial Documents"
        elif any(token.text.lower() in ["report", "thesis", "paper"] for token in doc):
            return "Academic Papers"
        else:
            return "Uncategorized"

    def organize_files(self):
        self.cursor.execute("SELECT filename, filepath, category FROM files")
        for filename, filepath, category in self.cursor.fetchall():
            category_path = os.path.join(self.base_path, category)
            os.makedirs(category_path, exist_ok=True)
            shutil.move(filepath, os.path.join(category_path, filename))

class DirectoryManagementApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Powered Directory Manager")
        self.setGeometry(100, 100, 800, 600)  # Adjusted for larger screens
        self.setMinimumSize(QSize(600, 400))  # Ensures proper scaling
        self.setStyleSheet(load_stylesheet())
        
        self.selected_directory = ""
        layout = QVBoxLayout()
        
        self.label = QLabel("Select a Directory to Organize:")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 12))
        layout.addWidget(self.label)
        
        self.select_button = QPushButton("Browse")
        self.select_button.clicked.connect(self.select_directory)
        layout.addWidget(self.select_button)
        
        self.organize_button = QPushButton("Organize Files")
        self.organize_button.clicked.connect(self.organize_files)
        layout.addWidget(self.organize_button)
        
        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.close)
        layout.addWidget(self.exit_button)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.setAcceptDrops(True) #commit 1 enable drag and drop
        
    
    def select_directory(self):
        self.selected_directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if self.selected_directory:
            self.label.setText(f"Selected: {self.selected_directory}")
    
    def organize_files(self):
        if not self.selected_directory:
            self.label.setText("Error: Please select a directory first.")
            return
        manager = AIDirectoryManager(self.selected_directory)
        manager.scan_directory()
        manager.organize_files()
        self.label.setText("Files have been organized successfully.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DirectoryManagementApp()
    window.showMaximized()
    sys.exit(app.exec_())
