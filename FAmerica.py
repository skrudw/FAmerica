import os
import sys
import requests
import zipfile
import subprocess
import threading
import ctypes
import json
import re
import winreg
import shutil
import psutil  
from io import BytesIO
import webbrowser  
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QPoint, QRectF, QUrl, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QMouseEvent, QPainter, QPainterPath, QRegion, QIcon, QPen, QDesktopServices
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QComboBox, QCheckBox, QPushButton, QTextEdit,
                             QMessageBox, QGroupBox, QProgressBar, QSystemTrayIcon, QMenu, QAction, QStyle)


ROOT_DIR = r"C:\FAmerica"
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")

if not os.path.exists(ROOT_DIR):
    os.makedirs(ROOT_DIR)

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.update_signal.emit("Downloading update...")
            response = requests.get(self.url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024 
            
            temp_zip = os.path.join(ROOT_DIR, "temp_update.zip")
            downloaded = 0
            with open(temp_zip, 'wb') as f:
                for data in response.iter_content(block_size):
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        progress = int(downloaded * 100 / total_size)
                        self.progress_signal.emit(progress)
                    
            self.update_signal.emit("Extracting...")
            with zipfile.ZipFile(temp_zip, 'r') as zf:
                zf.extractall(ROOT_DIR)
            
            os.remove(temp_zip)
            
            self.finished_signal.emit(True, "Update completed successfully")
        except Exception as e:
            self.finished_signal.emit(False, f"Error during update: {str(e)}")

class UpdateCheckerThread(QThread):
    update_available = pyqtSignal(str, str, bool) 
    error = pyqtSignal(str)

    def __init__(self, repo_url, current_version, parent=None):
        super().__init__(parent)
        self.repo_url = repo_url
        self.current_version = current_version

    def run(self):
        try:
            response = requests.get(self.repo_url)
            data = response.json()
            latest_version = data['tag_name']
            
            asset = next((a for a in data['assets'] if a['name'].endswith('.zip')), None)
            asset_url = asset['browser_download_url'] if asset else None
            
            is_available = self.current_version != latest_version and asset_url is not None
            self.update_available.emit(latest_version, asset_url, is_available)
                
        except Exception as e:
            self.error.emit(f"Error checking update: {str(e)}")

class ConsoleReaderThread(QThread):
    output_received = pyqtSignal(str)

    def __init__(self, process, parent=None):
        super().__init__(parent)
        self.process = process

    def run(self):
        try:
            while self.process.poll() is None:
                output = self.process.stdout.readline()
                if output:
                    self.output_received.emit(output.decode('cp866', errors='ignore').strip())
                    
            output = self.process.stdout.read()
            if output:
                self.output_received.emit(output.decode('cp866', errors='ignore').strip())
        except Exception as e:
            self.output_received.emit(f"Error reading console output: {str(e)}")

class CustomCheckBox(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QCheckBox {
                color: #FFFFFF;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                background-color: #2C2C2C;
                border: 1px solid #4A4A4A;
            }
            QCheckBox::indicator:checked {
                background-color: #4AFF95;
                border: 1px solid #4AFF95;
            }
        """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            
            rect = self.rect()
            indicator_x = rect.x() + 2 
            indicator_y = rect.y() + 2 + (rect.height() - 16) // 2
            
            painter.drawLine(int(indicator_x + 4 /1.2), int(indicator_y + 8/1.2), 
                           int(indicator_x + 8/1.2), int(indicator_y + 12/1.2))
            painter.drawLine(int(indicator_x + 8/1.2), int(indicator_y + 12/1.2), 
                           int(indicator_x + 12/1.2), int(indicator_y + 4/1.8))

class CustomMinimizeButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #2C2C2C;
                border-radius: 10px;
            }
        """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        
        rect = self.rect()
        center_y = rect.height() // 2
        painter.drawLine(6, center_y, 14, center_y)

class CustomCloseButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setStyleSheet("""
            QPushButton {
                background-color: #4AFF95;
                border: none;
                border-radius: 10px;
                color: #000000;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3AEF85;
            }
        """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        
        rect = self.rect()
        painter.drawLine(6, 6, 14, 14) 
        painter.drawLine(14, 6, 6, 14)

class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(50)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        
        self.title = QLabel("FAmerica")
        self.title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 14px; margin-top: 15px;")
        
        self.credits = QLabel("v0.1 created by skrudw")
        self.credits.setStyleSheet("color: #888888; font-size: 10px; margin-top: 15px;")
        
        self.telegram_btn = QPushButton()
        self.telegram_btn.setFixedSize(20, 20)
        self.telegram_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                                        
            }
            QPushButton:hover {
                background-color: #666666;
                border-radius: 10px;
            }
        """)
        self.telegram_btn.clicked.connect(lambda: self.open_url("https://t.me/skrudw"))
        
        self.github_btn = QPushButton()
        self.github_btn.setFixedSize(20, 20)
        self.github_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: #666666;
                border-radius: 10px;
            }
        """)
        self.github_btn.clicked.connect(lambda: self.open_url("https://github.com/"))
        
        telegram_icon_path = os.path.join(ROOT_DIR, "telegram.png")
        github_icon_path = os.path.join(ROOT_DIR, "github.png")
        
        if os.path.exists(telegram_icon_path):
            self.telegram_btn.setIcon(QIcon(telegram_icon_path))
            self.telegram_btn.setIconSize(QSize(16, 16))
        else:
            self.telegram_btn.setText("T")
            
        if os.path.exists(github_icon_path):
            self.github_btn.setIcon(QIcon(github_icon_path))
            self.github_btn.setIconSize(QSize(16, 16))
        else:
            self.github_btn.setText("G")
        
        self.minimize_btn = CustomMinimizeButton()
        self.minimize_btn.clicked.connect(self.parent.showMinimized)
        
        self.close_btn = CustomCloseButton()
        self.close_btn.clicked.connect(self.parent.hide_to_tray)
        
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.credits)  
        self.layout.addStretch()
        self.layout.addWidget(self.telegram_btn) 
        self.layout.addWidget(self.github_btn)    
        self.layout.addWidget(self.minimize_btn)
        self.layout.addWidget(self.close_btn)
        
        self.start = QPoint(0, 0)
        self.pressing = False

    def open_url(self, url):
        """Открывает URL в браузере по умолчанию"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            self.parent.update_log.emit(f"Error opening URL: {str(e)}")
class ZapretManager(QMainWindow):
    
    update_status = pyqtSignal(str)
    update_current_version = pyqtSignal(str)
    update_latest_version = pyqtSignal(str)
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    set_progress_visible = pyqtSignal(bool)
    set_buttons_enabled = pyqtSignal(bool, bool)  
    console_output = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.repo_url = "https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest"
        self.current_version = None
        self.latest_version = None
        self.process = None
        self.download_thread = None
        self.update_checker_thread = None
        self.console_reader_thread = None
        
        
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        
        if not self.is_admin():
            self.restart_as_admin()
            
        self.init_ui()
        self.setup_tray_icon()
        self.connect_signals()
        self.load_config()
        
        
        if self.auto_update_cb.isChecked():
            self.auto_update_on_start()

    def is_admin(self):
        """Проверяет, запущена ли программа с правами администратора"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def restart_as_admin(self):
        """Перезапускает программу с правами администратора"""
        if sys.argv[0].endswith('.py'):
            script = os.path.abspath(sys.argv[0])
            params = ' '.join([script] + sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        else:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, None, None, 1)
        sys.exit()

    def paintEvent(self, event):
        """Переопределяем метод отрисовки для закругленных углов"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(35, 35, 35))  
        
       
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        painter.drawPath(path)
        
        
        super().paintEvent(event)

    def setup_tray_icon(self):
        """Настраивает иконку в системном трее"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        
        tray_menu = QMenu()
        
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(open_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        """Обрабатывает активацию иконки в трее"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_from_tray()

    def hide_to_tray(self):
        """Скрывает окно в трей"""
        self.hide()
        self.tray_icon.showMessage(
            "FAmerica",
            "Я спрятался в трей",
            QSystemTrayIcon.Information,
            2000
        )

    def show_from_tray(self):
        """Показывает окно из трея"""
        self.show()
        self.activateWindow()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)

    def quit_application(self):
        """Полностью закрывает приложение"""
        self.stop_all_processes()
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """Обрабатывает событие закрытия окна"""
        event.ignore()
        self.hide_to_tray()

    def stop_all_processes(self):
        """Останавливает все связанные процессы"""
        try:
            if self.process and self.process.poll() is None:
                self.stop_process()
            
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'winws.exe' in proc.info['name'].lower():
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                        try:
                            proc.kill()
                        except psutil.NoSuchProcess:
                            pass
        except Exception as e:
            self.update_log.emit(f"Error stopping processes: {str(e)}")

    def init_ui(self):
        self.setWindowTitle("FAmerica")
        self.setFixedSize(500, 500)
        
        central_widget = QWidget()
        central_widget.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border-radius: 12px;
            }
        """)
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(15, 0, 15, 15)
        layout.setSpacing(15)
        
        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)
        
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #232323;
                color: #FFFFFF;
            }
            QLabel {
                color: #FFFFFF;
                font-size: 12px;
            }
            QComboBox {
                background-color: #464646 !important;
                color: #FFFFFF !important;
                border: none !important;
                border-radius: 5px !important;
                padding: 8px !important;
                font-size: 12px !important;
            }
            QComboBox::drop-down {
                border: none !important;
                width: 20px !important;
            }
            QComboBox::down-arrow {
                image: none !important;
                border-left: 5px solid transparent !important;
                border-right: 5px solid transparent !important;
                border-top: 5px solid #FFFFFF !important;
                margin-right: 5px !important;
            }
            QComboBox:hover {
                background-color: #5E5E5E !important;
            }
            QComboBox:pressed {
                background-color: #1F1F1F !important;
            }
            QComboBox QAbstractItemView {
                background-color: #1A1A1A;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                selection-background-color: #4AFF95;
                selection-color: #000000;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                border-radius: 3px;
                margin: 1px;
                background-color: #1A1A1A;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2C2C2C;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #4AFF95;
                color: #000000;
            }
            QCheckBox {
                color: #FFFFFF;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                background-color: #2C2C2C;
                border: 1px solid #4A4A4A;
            }
            QCheckBox::indicator:checked {
                background-color: #4AFF95;
                border: 1px solid #4AFF95;
            }
            QPushButton {
                background-color: #464646 !important;
                color: #FFFFFF !important;
                border: none !important;
                border-radius: 5px !important;
                padding: 10px 15px !important;
                font-size: 12px !important;
                font-weight: bold !important;
            }
            QPushButton:hover {
                background-color: #5E5E5E !important;
                color: #4AFF95 !important;
            }
            QPushButton:pressed {
                background-color: #1F1F1F !important;
                color: #4AFF95 !important;
            }
            QPushButton:disabled {
                background-color: #1A1A1A !important;
                color: #666666 !important;
            }
            QTextEdit {
                background-color: #2C2C2C;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QScrollBar:vertical {
                background-color: #2C2C2C;
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #4A4A4A;
                border-radius: 6px;
                min-height: 20px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5A5A5A;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background-color: transparent;
            }
            QScrollBar:horizontal {
                background-color: #2C2C2C;
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background-color: #4A4A4A;
                border-radius: 6px;
                min-width: 20px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #5A5A5A;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background-color: transparent;
            }
            QProgressBar {
                border: none;
                border-radius: 5px;
                text-align: center;
                background-color: #2C2C2C;
                color: #FFFFFF;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #4AFF95;
                border-radius: 5px;
            }
        """)
        
 
        top_section = QWidget()
        top_section.setStyleSheet("""
            QWidget {
                background-color: #2C2C2C;
                border-radius: 13px;
            }
        """)
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(15, 15, 15, 15)
        top_layout.setSpacing(10)
        

        versions_layout = QHBoxLayout()
        self.current_version_label = QLabel("Current Version: Unknown")
        versions_layout.addWidget(self.current_version_label)
        versions_layout.addStretch()
        self.latest_version_label = QLabel("Latest Version: Unknown")
        versions_layout.addWidget(self.latest_version_label)
        top_layout.addLayout(versions_layout)
        

        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Not running")
        self.status_label.setStyleSheet("color: #4AFF95; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        top_layout.addLayout(status_layout)
        

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        top_layout.addWidget(self.progress_bar)
        
        layout.addWidget(top_section)
        

        middle_section = QWidget()
        middle_section.setStyleSheet("""
            QWidget {
                background-color: #2C2C2C;
                border-radius: 13px;
            }
        """)
        middle_layout = QVBoxLayout(middle_section)
        middle_layout.setContentsMargins(15, 15, 15, 15)
        middle_layout.setSpacing(15)
        
        bat_layout = QHBoxLayout()
        bat_layout.addWidget(QLabel("Select BAT file:"))
        self.bat_combo = QComboBox()
        self.bat_combo.addItems(self.get_bat_files())
        self.bat_combo.setCurrentText("General.bat")
        self.bat_combo.currentTextChanged.connect(self.on_bat_change)
        self.bat_combo.setStyleSheet("""
            QComboBox {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #FFFFFF;
                margin-right: 5px;
            }
            QComboBox:hover {
                background-color: #5E5E5E;
            }
            QComboBox:pressed {
                background-color: #1F1F1F;
            }
            QComboBox QAbstractItemView {
                background-color: #1A1A1A;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                selection-background-color: #4AFF95;
                selection-color: #000000;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                border-radius: 3px;
                margin: 1px;
                background-color: #1A1A1A;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2C2C2C;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #4AFF95;
                color: #000000;
            }
        """)
        bat_layout.addWidget(self.bat_combo)
        middle_layout.addLayout(bat_layout)
        
        self.auto_update_cb = CustomCheckBox("Auto-update on start")
        self.auto_update_cb.setChecked(True)
        self.auto_update_cb.stateChanged.connect(self.on_auto_update_change)
        middle_layout.addWidget(self.auto_update_cb)
        
        self.auto_start_cb = CustomCheckBox("Auto-start with Windows")
        self.auto_start_cb.stateChanged.connect(self.on_auto_start_change)
        middle_layout.addWidget(self.auto_start_cb)
        
        
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        self.start_btn = QPushButton("START")
        self.start_btn.clicked.connect(self.start_process)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E5E5E;
                color: #4AFF95;
            }
            QPushButton:pressed {
                background-color: #1F1F1F;
                color: #4AFF95;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
            }
        """)
        buttons_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.clicked.connect(self.stop_process)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E5E5E;
                color: #4AFF95;
            }
            QPushButton:pressed {
                background-color: #1F1F1F;
                color: #4AFF95;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
            }
        """)
        buttons_layout.addWidget(self.stop_btn)
        
        self.check_update_btn = QPushButton("Check update")
        self.check_update_btn.clicked.connect(self.check_update)
        self.check_update_btn.setStyleSheet("""
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E5E5E;
                color: #4AFF95;
            }
            QPushButton:pressed {
                background-color: #1F1F1F;
                color: #4AFF95;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
            }
        """)
        buttons_layout.addWidget(self.check_update_btn)
        
        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self.update_app)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E5E5E;
                color: #4AFF95;
            }
            QPushButton:pressed {
                background-color: #1F1F1F;
                color: #4AFF95;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
            }
        """)
        buttons_layout.addWidget(self.update_btn)
        
        middle_layout.addLayout(buttons_layout)
        layout.addWidget(middle_section)
        
        bottom_section = QWidget()
        bottom_section.setStyleSheet("""
            QWidget {
                background-color: #2C2C2C;
                border-radius: 13px;
            }
        """)
        bottom_layout = QVBoxLayout(bottom_section)
        bottom_layout.setContentsMargins(15, 15, 15, 15)
        bottom_layout.setSpacing(10)
        
        bottom_layout.addWidget(QLabel("Logs:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        bottom_layout.addWidget(self.log_text)
        
        layout.addWidget(bottom_section)

    def connect_signals(self):
        """Подключает сигналы к слотам"""
        self.update_status.connect(self.status_label.setText)
        self.update_current_version.connect(lambda v: self.current_version_label.setText(f"Current Version: {v}"))
        self.update_latest_version.connect(lambda v: self.latest_version_label.setText(f"Latest Version: {v}"))
        self.update_log.connect(self.log_text.append)
        self.update_progress.connect(self.progress_bar.setValue)
        self.set_progress_visible.connect(self.progress_bar.setVisible)
        self.set_buttons_enabled.connect(self.set_buttons_state)
        self.console_output.connect(self.on_console_output)

    @pyqtSlot(str)
    def on_console_output(self, output):
        """Обрабатывает вывод из консоли"""
        if output:
            self.update_log.emit(f"Console: {output}")

    @pyqtSlot(bool, bool)
    def set_buttons_state(self, start_enabled, stop_enabled):
        """Устанавливает состояние кнопок"""
        self.start_btn.setEnabled(start_enabled)
        self.stop_btn.setEnabled(stop_enabled)

    @pyqtSlot(str)
    def on_bat_change(self, text):
        """Сохраняет выбор BAT-файла при изменении и перезапускает процесс, если он был запущен"""
        if self.process and self.process.poll() is None:
            self.update_log.emit(f"Stopping current process to switch to {text}")
            self.stop_process()
            
            QTimer.singleShot(1000, self.start_process)
        
        self.save_config()

    @pyqtSlot(int)
    def on_auto_update_change(self, state):
        """Сохраняет настройку автообновления при изменении"""
        self.save_config()

    @pyqtSlot(int)
    def on_auto_start_change(self, state):
        """Обрабатывает изменение настройки автозапуска"""
        if state == Qt.Checked:
            self.enable_autostart()
        else:
            self.disable_autostart()
        self.save_config()

    @pyqtSlot(int)
    def on_hide_console_change(self, state):
        """Обрабатывает изменение настройки скрытия консоли"""
        self.save_config()

    def enable_autostart(self):
        """Добавляет программу в автозагрузку Windows"""
        try:
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "FAmerica", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            
            self.update_log.emit("Autostart enabled")
        except Exception as e:
            self.update_log.emit(f"Error enabling autostart: {str(e)}")

    def disable_autostart(self):
        """Удаляет программу из автозагрузки Windows"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "FAmerica")
            winreg.CloseKey(key)
            
            self.update_log.emit("Autostart disabled")
        except Exception as e:
            self.update_log.emit(f"Error disabling autostart: {str(e)}")

    def check_autostart(self):
        """Проверяет, добавлена ли программа в автозагрузку"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_READ)
            
            if getattr(sys, 'frozen', False):
                current_path = sys.executable
            else:
                current_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            
            try:
                value, _ = winreg.QueryValueEx(key, "FAmerica")
                winreg.CloseKey(key)
                return value == current_path
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception as e:
            self.update_log.emit(f"Error checking autostart: {str(e)}")
            return False

    def auto_update_on_start(self):
        """Автоматически проверяет и устанавливает обновления при запуске"""
        self.update_log.emit("Checking for updates on startup...")
        self.check_update()

    def get_bat_files(self):
        bat_files = []
        try:
            for file in os.listdir(ROOT_DIR):
                if file.endswith('.bat'):
                    bat_files.append(file)
        except:
            pass
        
        if not bat_files:
            return [
                "general.bat",
                "discord.bat",
                "service.bat",
                "cloudflare_switch.bat",
                "general (ALT).bat",
                "general (ALT2).bat",
                "general (ALT3).bat",
                "general (ALT4).bat",
                "general (ALT5).bat",
                "general (ALT6).bat",
                "general (FAKE TLS).bat",
                "general (FAKE TLS ALT).bat",
                "general (FAKE TLS MOD).bat",
                "general (FAKE TLS AUTO).bat",
                "general (FAKE TLS MOD AUTO).bat",
                "general (FAKE TLS AUTO ALT).bat",
                "general (FAKE TLS AUTO ALT2).bat",
                "general (FAKE TLS MOD ALT).bat",
                "general (МГТС).bat",
                "general (МГТС2).bat"
            ]
        
        return bat_files

    def load_config(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    bat_file = config.get('default_bat', 'general.bat')
                    index = self.bat_combo.findText(bat_file)
                    if index >= 0:
                        self.bat_combo.setCurrentIndex(index)
                    self.current_version = config.get('version')
                    self.update_current_version.emit(self.current_version or "Unknown")
                    self.auto_update_cb.setChecked(config.get('auto_update', True))
                    
                    auto_start = config.get('auto_start', True)
                    self.auto_start_cb.setChecked(auto_start)
                    

                    
                    if auto_start:
                        if not self.check_autostart():
                            self.enable_autostart()
                    else:
                        if self.check_autostart():
                            self.disable_autostart()
            else:
                self.detect_version_from_files()
                self.auto_update_cb.setChecked(True)
                self.auto_start_cb.setChecked(True)  
                self.enable_autostart()
        except Exception as e:
            self.update_log.emit(f"Error loading config: {str(e)}")
            self.bat_combo.setCurrentIndex(0)
            self.auto_update_cb.setChecked(True)
            self.auto_start_cb.setChecked(True)


    def detect_version_from_files(self):
        """Пытается определить версию из существующих файлов"""
        try:
            for file in os.listdir(ROOT_DIR):
                if 'zapret-discord-youtube' in file and file.endswith('.zip'):
                    match = re.search(r'zapret-discord-youtube-(\d+\.\d+\.\d+)', file)
                    if match:
                        self.current_version = match.group(1)
                        self.update_current_version.emit(self.current_version)
                        break
        except:
            pass

    def save_config(self):
        config = {
            'default_bat': self.bat_combo.currentText(),
            'version': self.current_version,
            'auto_update': self.auto_update_cb.isChecked(),
            'auto_start': self.auto_start_cb.isChecked(),
        }
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f)

    def check_update(self):
        """Проверяет обновления в отдельном потоке"""
        self.update_checker_thread = UpdateCheckerThread(self.repo_url, self.current_version)
        self.update_checker_thread.update_available.connect(self.on_update_available)
        self.update_checker_thread.error.connect(self.update_log.emit)
        self.update_checker_thread.start()

    @pyqtSlot(str, str, bool)
    def on_update_available(self, latest_version, asset_url, is_available):
        """Обрабатывает результат проверки обновлений"""
        self.latest_version = latest_version
        self.update_latest_version.emit(self.latest_version)
        
        if is_available:
            self.update_log.emit(f"New version available: {self.latest_version}")
            if self.auto_update_cb.isChecked():
                self.update_log.emit(f"Downloading {asset_url}...")
                self.update_status.emit("Downloading update...")
                self.download_and_extract(asset_url)
        else:
            self.update_log.emit("Already up to date")
            self.update_status.emit("Up to date")
            if self.auto_update_cb.isChecked():
                QTimer.singleShot(1000, self.start_process)

    def update_app(self):
        """Запускает проверку обновлений и установку"""
        self.check_update()

    def download_and_extract(self, url):
        """Запускает поток для скачивания и распаковки"""
        self.set_progress_visible.emit(True)
        self.update_progress.emit(0)
        
        self.download_thread = DownloadThread(url)
        self.download_thread.update_signal.connect(self.update_status.emit)
        self.download_thread.progress_signal.connect(self.update_progress.emit)
        self.download_thread.finished_signal.connect(self.on_download_finished)
        self.download_thread.start()

    @pyqtSlot(bool, str)
    def on_download_finished(self, success, message):
        """Обрабатывает завершение загрузки"""
        self.set_progress_visible.emit(False)
        self.update_log.emit(message)
        if success:
            self.current_version = self.latest_version
            self.update_current_version.emit(self.current_version)
            self.modify_bat_files()
            self.save_config()
            if self.auto_update_cb.isChecked():
                QTimer.singleShot(1000, self.start_process)

    def modify_bat_files(self):
        """Модифицирует BAT-файлы для скрытия консоли winws.exe"""
        try:
            for bat_file in self.get_bat_files():
                bat_path = os.path.join(ROOT_DIR, bat_file)
                if os.path.exists(bat_path):
                    self.modify_bat_file(bat_path)
            self.update_log.emit("BAT files modified successfully")
        except Exception as e:
            self.update_log.emit(f"Error modifying BAT files: {str(e)}")

    def modify_bat_file(self, file_path):
        """Модифицирует конкретный BAT-файл для скрытия консоли winws.exe"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            new_content = content
            if 'start "zapret: %~n0" /min' in content and 'winws.exe' in content:
                new_content = content.replace('start "zapret: %~n0" /min', '')
                self.update_log.emit(f"Modified {os.path.basename(file_path)}")

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
        except Exception as e:
            self.update_log.emit(f"Error modifying {file_path}: {str(e)}")

    def start_process(self):
        if self.process and self.process.poll() is None:
            self.update_log.emit("Process is already running")
            return

        bat_file = os.path.join(ROOT_DIR, self.bat_combo.currentText())
        if not os.path.exists(bat_file):
            self.update_log.emit(f"File {bat_file} not found")
            return

        try:
            startupinfo = None
            creationflags = 0
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 
            creationflags = subprocess.CREATE_NO_WINDOW
            
            self.process = subprocess.Popen(
                ['cmd.exe', '/c', bat_file],
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            self.update_status.emit("Running")
            self.update_log.emit(f"Started {bat_file}")
            self.set_buttons_enabled.emit(False, True)
            
            self.console_reader_thread = ConsoleReaderThread(self.process)
            self.console_reader_thread.output_received.connect(self.console_output.emit)
            self.console_reader_thread.start()
            
            threading.Thread(target=self.monitor_process, daemon=True).start()
        except Exception as e:
            self.update_log.emit(f"Error starting process: {str(e)}")

    def stop_process(self):
        if self.process:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], check=True)
                self.update_status.emit("Stopped")
                self.update_log.emit("Process stopped")
                self.set_buttons_enabled.emit(True, False)
            except subprocess.CalledProcessError:
                self.update_log.emit("Error stopping process")
            except Exception as e:
                self.update_log.emit(f"Error: {str(e)}")

    def monitor_process(self):
        try:
            self.process.wait()
            self.update_status.emit("Not running")
            self.update_log.emit("Process finished")
            self.set_buttons_enabled.emit(True, False)
        except Exception as e:
            self.update_log.emit(f"Error monitoring process: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  
    
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(70, 70, 70)) 
    dark_palette.setColor(QPalette.AlternateBase, QColor(70, 70, 70)) 
    dark_palette.setColor(QPalette.ToolTipBase, QColor(70, 70, 70)) 
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(70, 70, 70))  
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, QColor(74, 255, 149)) 
    dark_palette.setColor(QPalette.Link, QColor(74, 255, 149)) 
    dark_palette.setColor(QPalette.Highlight, QColor(74, 255, 149)) 
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    manager = ZapretManager()
    manager.show()
    sys.exit(app.exec_())