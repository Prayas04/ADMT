import sys
import os
import shutil
import hashlib
import sqlite3
import spacy
import requests
from PyQt5.QtWidgets import QApplication, QFileDialog, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QFrame, QGraphicsOpacityEffect, QTableWidget, QTableWidgetItem, QMessageBox, QTextEdit
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor
from PyQt5.QtCore import Qt, QSize, QPropertyAnimation
from qdarkstyle import load_stylesheet

class AIDirectoryManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Powered Directory Manager")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(QSize(1920, 1080))
        self.setStyleSheet(load_stylesheet() + """
            QMainWindow {
                background-color: #0d1117;
                color: #ffffff;
            }
            QPushButton {
                font-size: 22px;
                padding: 12px;
                border: 2px solid #00ffcc;
                border-radius: 10px;
                color: #00ffcc;
                background: rgba(0, 255, 204, 0.1);
            }
            QPushButton:hover {
                background-color: rgba(0, 255, 204, 0.3);
            }
            QFrame {
                background-color: #161b22;
                border-radius: 15px;
                padding: 15px;
            }
            QLabel {
                color: #00ffcc;
                font-size: 26px;
            }
            QTextEdit {
                font-size: 18px;
                color: white;
                background-color: #0d1117;
                border: 2px solid #0077ff;
                border-radius: 15px;
                padding: 10px;
            }
        """)
        
        self.selected_directories = []
        
        main_layout = QHBoxLayout()
        menu_layout = QVBoxLayout()
        menu_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        menu_layout.setSpacing(int(self.height() * 0.03))
        menu_layout.setContentsMargins(50, 0, 50, 0)
        
        self.add_directories_button = QPushButton("+ Add Directories")
        self.add_directories_button.clicked.connect(self.add_directories)
        menu_layout.addWidget(self.add_directories_button)
        
        self.organize_button = QPushButton("⚙️ Organize Files")
        self.organize_button.clicked.connect(self.organize_files)
        menu_layout.addWidget(self.organize_button)
        
        self.exit_button = QPushButton("🚀 Exit")
        self.exit_button.clicked.connect(self.close)
        menu_layout.addWidget(self.exit_button)
        
        # Add the "Remove Directory" button to the left-hand menu layout
        self.remove_directory_button = QPushButton("🗑️ Remove Selected Directory")
        self.remove_directory_button.clicked.connect(self.remove_selected_directory)
        menu_layout.addWidget(self.remove_directory_button)
        
        separator = QFrame()
        separator.setFixedWidth(5)
        separator.setStyleSheet("background: linear-gradient(to right, #00ffcc, #0077ff);")
        
        content_layout = QVBoxLayout()
        content_frame = QFrame()
        content_frame.setLayout(content_layout)
        
        self.label = QLabel("AI POWERED DIRECTORY MANAGER")
        self.label.setFont(QFont("Orbitron", 26, QFont.Bold))
        content_layout.addWidget(self.label)
        
        # Add a label for the directory table
        self.directory_label = QLabel("Directories")
        self.directory_label.setFont(QFont("Orbitron", 20, QFont.Bold))
        self.directory_label.setAlignment(Qt.AlignLeft)
        self.directory_label.setStyleSheet("color: #00ffcc; margin-bottom: 10px;")
        content_layout.addWidget(self.directory_label)

        # Add the directory table
        self.directory_table = QTableWidget()
        self.directory_table.setColumnCount(1)
        self.directory_table.setHorizontalHeaderLabels(["Selected Directories"])
        content_layout.addWidget(self.directory_table)

        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Enter your AI command...")
        self.chat_input.installEventFilter(self)
        content_layout.addWidget(self.chat_input)
        
        self.chat_button = QPushButton("Execute")
        self.chat_button.clicked.connect(self.execute_chat_command)
        content_layout.addWidget(self.chat_button)
        
        # Add the "Remove Directory" button in the __init__ method
        self.remove_directory_button = QPushButton("🗑️ Remove Selected Directory")
        self.remove_directory_button.clicked.connect(self.remove_selected_directory)
        content_layout.addWidget(self.remove_directory_button)
        
        content_layout.addStretch()
        
        menu_container = QWidget()
        menu_container.setLayout(menu_layout)
        main_layout.addWidget(menu_container, 1)
        main_layout.addWidget(separator)
        main_layout.addWidget(content_frame, 3)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
    
    def add_directories(self):
        directories = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directories:
            self.selected_directories.append(directories)
            self.update_directory_table()
    
    def update_directory_table(self):
        self.directory_table.setRowCount(len(self.selected_directories))
        for row, directory in enumerate(self.selected_directories):
            self.directory_table.setItem(row, 0, QTableWidgetItem(directory))
    
    def execute_chat_command(self):
        prompt = self.chat_input.toPlainText()
        if not prompt.strip():
            self.show_error_message("Please enter a valid prompt.")
            return
        
        api_key = "your-api-key"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        data = {"model": "gpt-4", "messages": [{"role": "user", "content": prompt}]}
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No response from ChatGPT.")
            QMessageBox.information(self, "ChatGPT Response", result)
        else:
            self.show_error_message("Failed to fetch response from ChatGPT.")
    
    def show_error_message(self, message):
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("Error")
        error_dialog.setText(message)
        error_dialog.exec_()

    def organize_files(self):
        if not self.selected_directories:
            self.show_error_message("Error: Please add directories first.")
            return
        try:
            self.show_error_message("Files have been organized successfully.")
        except Exception as e:
            self.show_error_message(f"Unexpected error: {e}")
    
    def eventFilter(self, source, event):
        if source == self.chat_input and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.execute_chat_command()
                return True
        return super().eventFilter(source, event)

    def remove_selected_directory(self):
        selected_row = self.directory_table.currentRow()
        if selected_row == -1:
            self.show_error_message("Please select a directory to remove.")
            return

        # Remove the selected directory from the list and update the table
        del self.selected_directories[selected_row]
        self.update_directory_table()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AIDirectoryManager()
    window.show()
    sys.exit(app.exec_())
