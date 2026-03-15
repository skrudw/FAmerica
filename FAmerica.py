import os
import sys
import asyncio
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
import time  
from io import BytesIO
import webbrowser  
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QPoint, QRectF, QUrl, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QMouseEvent, QPainter, QPainterPath, QRegion, QIcon, QPen, QDesktopServices
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QComboBox, QCheckBox, QPushButton, QTextEdit,
                             QMessageBox, QGroupBox, QProgressBar, QSystemTrayIcon, QMenu, QAction, QStyle, QScrollArea,
                             QStackedWidget, QFrame, QSpinBox, QPlainTextEdit)
import configparser
from packaging import version
from urllib.parse import unquote
def download_icons_if_missing():
    """Скачивает иконки, если они отсутствуют в папке C:/FAmerica/"""
    icons = {
        'github.png': 'https://github.com/skrudw/FAmerica/raw/main/img/github.png',
        'telegram.png': 'https://github.com/skrudw/FAmerica/raw/main/img/telegram.png'
    }
    
    for icon_name, icon_url in icons.items():
        icon_path = os.path.join(ROOT_DIR, icon_name)
        if not os.path.exists(icon_path):
            try:
                response = requests.get(icon_url, timeout=10)
                response.raise_for_status()
                with open(icon_path, 'wb') as f:
                    f.write(response.content)
                print(f"Downloaded {icon_name}")
            except Exception as e:
                print(f"Error downloading {icon_name}: {str(e)}")
def check_for_update():
    # Проверяем флаг игнорирования обновлений
    if not ENABLE_FAmerica_AUTO_UPDATE:
        print("Автоматическое обновление FAmerica отключено (ENABLE_FAmerica_AUTO_UPDATE = False)")
        return
    
    config = configparser.ConfigParser()
    config.read('C:/FAmerica/config.ini')
    current_ver = config.get('Program', 'version', fallback='0.0.0')
    
    api_url = "https://api.github.com/repos/skrudw/FAmerica/releases/latest"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        latest_release = response.json()
        
        exe_asset = None
        for asset in latest_release.get('assets', []):
            if asset['name'].endswith('.exe'):
                exe_asset = asset
                break
        
        if not exe_asset:
            print("EXE файл не найден в активах релиза")
            return

        filename = unquote(exe_asset['name'])
        version_match = re.search(r'v?(\d+\.\d+(?:\.\d+)?)', filename)
        if not version_match:
            print(f"Не удалось извлечь версию из文件名: {filename}")
            return
            
        latest_ver = version_match.group(1)
        
        if version.parse(latest_ver) > version.parse(current_ver):
            print(f"Найдена новая версия: {latest_ver}")
            download_and_update(exe_asset['browser_download_url'], filename, latest_ver)
        else:
            print("У вас актуальная версия программы")
            
    except Exception as e:
        print(f"Ошибка при проверке обновлений: {str(e)}")

def download_and_update(asset_url, filename, new_version):
    try:
        response = requests.get(asset_url, stream=True)
        response.raise_for_status()
        
        new_exe_name = f"FAmerica-{new_version}.exe"
        with open(new_exe_name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        config = configparser.ConfigParser()
        config.read('C:/FAmerica/config.ini')
        if not config.has_section('Program'):
            config.add_section('Program')
        config.set('Program', 'version', new_version)
        with open('C:/FAmerica/config.ini', 'w') as configfile:
            config.write(configfile)
        
        subprocess.Popen([new_exe_name] + sys.argv[1:])
        sys.exit(0)
        
    except Exception as e:
        print(f"Ошибка при обновлении: {str(e)}")
ROOT_DIR = r"C:\FAmerica"
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")

try:
    import tg_ws_proxy
    TG_PROXY_AVAILABLE = True
except Exception:
    tg_ws_proxy = None
    TG_PROXY_AVAILABLE = False

# Флаг для игнорирования автоматической проверки обновлений FAmerica
# Установите в False, чтобы отключить автоматическое обновление при запуске
ENABLE_FAmerica_AUTO_UPDATE = True

if not os.path.exists(ROOT_DIR):
    os.makedirs(ROOT_DIR)

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.parent_manager = parent

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
            
            # Перед распаковкой еще раз пытаемся остановить процессы zapret
            # на случай, если они были запущены во время загрузки
            try:
                # Останавливаем процессы winws.exe через taskkill
                subprocess.run(['taskkill', '/F', '/IM', 'winws.exe'], 
                             capture_output=True, timeout=5)
            except:
                pass
            
            # Даем немного времени на завершение процессов
            time.sleep(1)
            
            try:
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    zf.extractall(ROOT_DIR)
            except PermissionError as e:
                # Если все еще есть ошибка доступа, предлагаем перезагрузку
                self.finished_signal.emit(False, 
                    f"Ошибка доступа к файлам: {str(e)}\n"
                    "Файлы zapret используются другим процессом.\n"
                    "Попробуйте закрыть все программы, использующие zapret, и повторите обновление.")
                return
            
            os.remove(temp_zip)
            
            self.finished_signal.emit(True, "Update completed successfully")
        except Exception as e:
            self.finished_signal.emit(False, f"Error during update: {str(e)}")

class IpsetUpdateThread(QThread):
    """Поток обновления ipset; по завершении (успех или ошибка) излучает finished()."""
    log_msg = pyqtSignal(str)

    def __init__(self, parent_manager=None):
        super().__init__(parent_manager)
        self.manager = parent_manager

    def run(self):
        try:
            lists_dir = os.path.join(ROOT_DIR, "lists")
            if not os.path.exists(lists_dir):
                os.makedirs(lists_dir)
            list_file = os.path.join(lists_dir, "ipset-all.txt")
            url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt"
            self.log_msg.emit(f"Updating ipset-all from {url}...")
            try:
                response = requests.get(url, timeout=15)
                response.raise_for_status()
                backup_file = f"{list_file}.backup"
                old_content = None
                if os.path.exists(list_file):
                    try:
                        with open(list_file, 'r', encoding='utf-8') as f:
                            old_content = f.read().strip()
                            if old_content and old_content != "203.0.113.113/32":
                                with open(backup_file, 'w', encoding='utf-8') as bf:
                                    bf.write(old_content)
                    except Exception:
                        pass
                if not old_content or old_content == "203.0.113.113/32" or not os.path.exists(backup_file):
                    with open(backup_file, 'w', encoding='utf-8') as bf:
                        bf.write(response.text)
                with open(list_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                self.log_msg.emit(f"Successfully updated ipset list (backup saved, {len(response.text)} bytes)")
                self.log_msg.emit("ipset update finished")
            except requests.exceptions.RequestException as e:
                self.log_msg.emit(f"Error downloading ipset list: {str(e)}")
                self.log_msg.emit("ipset update failed")
        except Exception as e:
            self.log_msg.emit(f"Error during ipset update: {str(e)}")

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


class TelegramProxyThread(QThread):
    """Запускает Telegram WebSocket proxy в отдельном потоке с asyncio."""
    error_signal = pyqtSignal(str)

    def __init__(self, port, dc_opt, host="127.0.0.1", parent=None):
        super().__init__(parent)
        self.port = port
        self.dc_opt = dc_opt
        self.host = host
        self._loop = None
        self._stop_ev = None

    def run(self):
        if not TG_PROXY_AVAILABLE or tg_ws_proxy is None:
            self.error_signal.emit("Модуль tg_ws_proxy или cryptography не установлен.")
            return
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_ev = asyncio.Event()
        try:
            self._loop.run_until_complete(
                tg_ws_proxy._run(self.port, self.dc_opt, stop_event=self._stop_ev, host=self.host)
            )
        except Exception as e:
            self.error_signal.emit(str(e))
        finally:
            self._loop.close()
            self._loop = None
            self._stop_ev = None

    def request_stop(self):
        if self._loop and self._stop_ev:
            self._loop.call_soon_threadsafe(self._stop_ev.set)


class BatFileComboBox(QComboBox):
    """Кастомный ComboBox для выбора BAT файлов с автообновлением списка"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_manager = parent
    
    def showPopup(self):
        """Переопределяем для обновления списка перед показом"""
        if self.parent_manager:
            # Сохраняем текущий выбранный файл
            current_text = self.currentText()
            
            # Очищаем список
            self.clear()
            
            # Получаем обновленный список BAT файлов
            bat_files = self.parent_manager.get_bat_files()
            self.addItems(bat_files)
            
            # Восстанавливаем выбранный файл, если он все еще существует
            index = self.findText(current_text)
            if index >= 0:
                self.setCurrentIndex(index)
            else:
                # Если выбранного файла больше нет, выбираем первый или сохраняем последний выбранный
                if self.count() > 0:
                    self.setCurrentIndex(0)
        
        # Вызываем стандартный метод показа списка
        super().showPopup()

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

class LeftSidebar(QWidget):
    """Левая панель 160px с иконкой, табами и кнопками. Поддержка перетаскивания окна."""
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setFixedWidth(160)
        self.setStyleSheet("background-color: #191919;")
        self._drag_start = QPoint(0, 0)
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        self.close_btn = CustomCloseButton(self)
        self.close_btn.clicked.connect(self.main_window.hide_to_tray)
        top_row.addWidget(self.close_btn)
        top_row.addStretch()
        layout.addLayout(top_row)
        layout.addSpacing(4)

        self.icon_label = QLabel("FAmerica")
        self.icon_label.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)
        layout.addSpacing(12)

        tab_style = """
            QPushButton {
                background-color: #252525;
                color: #AAAAAA;
                border: none;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 11px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #2D2D2D;
                color: #FFFFFF;
            }
            QPushButton:checked {
                background-color: #333333;
                color: #FFFFFF;
            }
        """
        self.tab_zapret = QPushButton("Zapret - discord, youtube")
        self.tab_zapret.setCheckable(True)
        self.tab_zapret.setChecked(True)
        self.tab_zapret.setStyleSheet(tab_style)
        self._zapret_marquee_text = "Zapret - discord, youtube"
        self._zapret_marquee_index = 0
        self._zapret_marquee_len = 22
        self._zapret_marquee_paused = False
        self._zapret_marquee_timer = QTimer(self)
        self._zapret_marquee_timer.timeout.connect(self._update_zapret_marquee)
        self._zapret_marquee_timer.start(250)
        self.tab_telegram = QPushButton("Telegram Fix")
        self.tab_telegram.setCheckable(True)
        self.tab_telegram.setStyleSheet(tab_style)
        self.tab_settings = QPushButton("Settings")
        self.tab_settings.setCheckable(True)
        self.tab_settings.setStyleSheet(tab_style)

        layout.addWidget(self.tab_zapret)
        layout.addWidget(self.tab_telegram)
        layout.addWidget(self.tab_settings)
        layout.addStretch()

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(6)
        self.telegram_btn = QPushButton()
        self.telegram_btn.setFixedSize(24, 24)
        self.telegram_btn.setStyleSheet("QPushButton { background-color: transparent; border: none; } QPushButton:hover { background-color: #333; border-radius: 12px; }")
        self.telegram_btn.clicked.connect(lambda: self._open_url("https://t.me/famerica_channel"))
        self.github_btn = QPushButton()
        self.github_btn.setFixedSize(24, 24)
        self.github_btn.setStyleSheet("QPushButton { background-color: transparent; border: none; } QPushButton:hover { background-color: #333; border-radius: 12px; }")
        self.github_btn.clicked.connect(lambda: self._open_url("https://github.com/skrudw/FAmerica/"))
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
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.telegram_btn)
        bottom_layout.addWidget(self.github_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

    def _update_zapret_marquee(self):
        if self._zapret_marquee_paused:
            return
        padded = self._zapret_marquee_text + "    " + self._zapret_marquee_text
        n = len(self._zapret_marquee_text) + 4
        start = self._zapret_marquee_index % n
        self.tab_zapret.setText(padded[start:start + self._zapret_marquee_len])
        if self._zapret_marquee_index == 0:
            self._zapret_marquee_paused = True
            self._zapret_marquee_timer.stop()
            QTimer.singleShot(5000, self._zapret_marquee_resume)
            return
        self._zapret_marquee_index = (self._zapret_marquee_index + 1) % n

    def _zapret_marquee_resume(self):
        self._zapret_marquee_index = 1
        self._zapret_marquee_paused = False
        self._zapret_marquee_timer.start(250)

    def _open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception as e:
            self.main_window.update_log.emit(f"Error opening URL: {str(e)}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos() - self.window().frameGeometry().topLeft()
            self._dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPos() - self._drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)


class TitleBar(QWidget):
    """Заголовок для других окон (например Settings)."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(50)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        
        self.title = QLabel("FAmerica")
        self.title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 14px; margin-top: 15px;")
        
        self.credits = QLabel("v0.5 created by skrudw")
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
        self.telegram_btn.clicked.connect(lambda: self.open_url("https://t.me/famerica_channel"))
        
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
        self.github_btn.clicked.connect(lambda: self.open_url("https://github.com/skrudw/FAmerica/"))
        
        self.settings_btn = QPushButton("service")
        self.settings_btn.setFixedSize(70, 25)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                border: none;
                color: #FFFFFF !important;
                font-size: 11px;
                font-weight: normal;
                padding: 2px 5px;
            }
            QPushButton:hover {
                background-color: #666666;
                border-radius: 5px;
            }
        """)
        self.settings_btn.setToolTip("Service Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        
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
        self.layout.addWidget(self.settings_btn)
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
    
    def open_settings(self):
        """Открывает окно настроек"""
        if not hasattr(self.parent, 'settings_window') or self.parent.settings_window is None:
            self.parent.settings_window = SettingsWindow(self.parent)
        self.parent.settings_window.show()
        self.parent.settings_window.raise_()
        self.parent.settings_window.activateWindow()

class SettingsWindow(QMainWindow):
    """Окно настроек с функциями из service.bat"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_manager = parent
        self.setWindowTitle("FAmerica Settings")
        self.setFixedSize(600, 700)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Заголовок
        title = QLabel("Service Settings")
        title.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Область с кнопками
        scroll_area = QTextEdit()
        scroll_area.setReadOnly(True)
        scroll_area.setStyleSheet("""
            QTextEdit {
                background-color: #2C2C2C;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        self.log_output = scroll_area
        layout.addWidget(scroll_area)
        
        # Кнопки
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)
        
        # Строка 1
        row1 = QHBoxLayout()
        self.btn_install = QPushButton("1. Install Service")
        self.btn_remove = QPushButton("2. Remove Services")
        self.btn_status = QPushButton("3. Check Status")
        row1.addWidget(self.btn_install)
        row1.addWidget(self.btn_remove)
        row1.addWidget(self.btn_status)
        buttons_layout.addLayout(row1)
        
        # Строка 2
        row2 = QHBoxLayout()
        self.btn_diagnostics = QPushButton("4. Run Diagnostics")
        self.btn_check_updates = QPushButton("5. Check Updates")
        row2.addWidget(self.btn_diagnostics)
        row2.addWidget(self.btn_check_updates)
        buttons_layout.addLayout(row2)
        
        # Строка 3
        row3 = QHBoxLayout()
        self.btn_toggle_check_updates = QPushButton("6. Toggle Check Updates")
        self.btn_toggle_game_filter = QPushButton("7. Toggle Game Filter")
        row3.addWidget(self.btn_toggle_check_updates)
        row3.addWidget(self.btn_toggle_game_filter)
        buttons_layout.addLayout(row3)
        
        # Строка 4
        row4 = QHBoxLayout()
        self.btn_toggle_ipset = QPushButton("8. Toggle ipset")
        self.btn_update_ipset = QPushButton("9. Update ipset list")
        row4.addWidget(self.btn_toggle_ipset)
        row4.addWidget(self.btn_update_ipset)
        buttons_layout.addLayout(row4)
        
        # Строка 5
        row5 = QHBoxLayout()
        self.btn_update_hosts = QPushButton("10. Update hosts file")
        self.btn_run_tests = QPushButton("11. Run Tests")
        row5.addWidget(self.btn_update_hosts)
        row5.addWidget(self.btn_run_tests)
        buttons_layout.addLayout(row5)
        
        layout.addLayout(buttons_layout)
        
        # Подключаем сигналы
        self.btn_install.clicked.connect(self.install_service)
        self.btn_remove.clicked.connect(self.remove_services)
        self.btn_status.clicked.connect(self.check_status)
        self.btn_diagnostics.clicked.connect(self.run_diagnostics)
        self.btn_check_updates.clicked.connect(self.check_updates)
        self.btn_toggle_check_updates.clicked.connect(self.toggle_check_updates)
        self.btn_toggle_game_filter.clicked.connect(self.toggle_game_filter)
        self.btn_toggle_ipset.clicked.connect(self.toggle_ipset)
        self.btn_update_ipset.clicked.connect(self.update_ipset_list)
        self.btn_update_hosts.clicked.connect(self.update_hosts)
        self.btn_run_tests.clicked.connect(self.run_tests)
        
        # Применяем стили
        self.setStyleSheet("""
            QMainWindow {
                background-color: #232323;
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E5E5E;
                color: #4AFF95;
            }
            QPushButton:pressed {
                background-color: #1F1F1F;
            }
        """)
        
        # Обновляем статусы
        self.update_statuses()
    
    def log(self, message):
        """Добавляет сообщение в лог"""
        self.log_output.append(message)
    
    def update_statuses(self):
        """Обновляет статусы переключателей"""
        # Обновляем текст кнопок с текущими статусами
        try:
            # Check Updates status
            check_updates_flag = os.path.join(ROOT_DIR, "utils", "check_updates.enabled")
            check_updates_status = "enabled" if os.path.exists(check_updates_flag) else "disabled"
            self.btn_toggle_check_updates.setText(f"6. Toggle Check Updates ({check_updates_status})")
            
            # Game Filter status
            game_filter_flag = os.path.join(ROOT_DIR, "utils", "game_filter.enabled")
            game_filter_status = "enabled" if os.path.exists(game_filter_flag) else "disabled"
            self.btn_toggle_game_filter.setText(f"7. Toggle Game Filter ({game_filter_status})")
            
            # ipset status
            list_file = os.path.join(ROOT_DIR, "lists", "ipset-all.txt")
            if os.path.exists(list_file):
                with open(list_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        ipset_status = "any"
                    elif content == "203.0.113.113/32":
                        ipset_status = "none"
                    else:
                        ipset_status = "loaded"
            else:
                ipset_status = "any"
            self.btn_toggle_ipset.setText(f"8. Toggle ipset ({ipset_status})")
        except Exception as e:
            self.log(f"Error updating statuses: {str(e)}")
    
    def install_service(self):
        """Устанавливает сервис zapret"""
        self.log("=== Install Service ===")
        self.log("This function requires selecting a BAT file from service.bat")
        self.log("Please use the main window to start a BAT file, or run service.bat manually")
        self.log("")
    
    def remove_services(self):
        """Удаляет сервисы zapret"""
        self.log("=== Remove Services ===")
        try:
            # Останавливаем сервис zapret
            result = subprocess.run(['sc', 'query', 'zapret'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                subprocess.run(['net', 'stop', 'zapret'], capture_output=True, timeout=10)
                subprocess.run(['sc', 'delete', 'zapret'], capture_output=True, timeout=5)
                self.log("✓ zapret service stopped and removed")
            else:
                self.log("zapret service not found")
            
            # Останавливаем процессы winws.exe
            subprocess.run(['taskkill', '/F', '/IM', 'winws.exe'], capture_output=True, timeout=5)
            self.log("✓ winws.exe processes stopped")
            
            # Удаляем сервисы WinDivert
            for service_name in ['WinDivert', 'WinDivert14']:
                result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    subprocess.run(['net', 'stop', service_name], capture_output=True, timeout=10)
                    subprocess.run(['sc', 'delete', service_name], capture_output=True, timeout=5)
                    self.log(f"✓ {service_name} service stopped and removed")
            
            self.log("Services removal completed")
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def check_status(self):
        """Проверяет статус сервисов"""
        self.log("=== Check Status ===")
        try:
            # Проверка сервиса zapret
            result = subprocess.run(['sc', 'query', 'zapret'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                if 'RUNNING' in result.stdout:
                    self.log("✓ zapret service is RUNNING")
                else:
                    self.log("✗ zapret service is NOT running")
            else:
                self.log("✗ zapret service is NOT installed")
            
            # Проверка процессов winws.exe
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq winws.exe'], 
                                  capture_output=True, text=True, timeout=5)
            if 'winws.exe' in result.stdout:
                self.log("✓ winws.exe is RUNNING")
            else:
                self.log("✗ winws.exe is NOT running")
            
            # Проверка WinDivert
            result = subprocess.run(['sc', 'query', 'WinDivert'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                if 'RUNNING' in result.stdout:
                    self.log("✓ WinDivert service is RUNNING")
                else:
                    self.log("✗ WinDivert service is NOT running")
            else:
                self.log("WinDivert service not found")
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def run_diagnostics(self):
        """Запускает диагностику"""
        self.log("=== Run Diagnostics ===")
        self.log("Running diagnostics...")
        try:
            # Проверка Base Filtering Engine
            result = subprocess.run(['sc', 'query', 'BFE'], capture_output=True, text=True, timeout=5)
            if 'RUNNING' in result.stdout:
                self.log("✓ Base Filtering Engine is running")
            else:
                self.log("✗ Base Filtering Engine is NOT running")
            
            # Проверка TCP timestamps
            result = subprocess.run(['netsh', 'interface', 'tcp', 'show', 'global'], 
                                  capture_output=True, text=True, timeout=5)
            if 'timestamps' in result.stdout.lower() and 'enabled' in result.stdout.lower():
                self.log("✓ TCP timestamps are enabled")
            else:
                self.log("✗ TCP timestamps are disabled")
                subprocess.run(['netsh', 'interface', 'tcp', 'set', 'global', 'timestamps=enabled'], 
                             capture_output=True, timeout=5)
                self.log("  → Attempted to enable TCP timestamps")
            
            # Проверка процессов Adguard
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq AdguardSvc.exe'], 
                                  capture_output=True, text=True, timeout=5)
            if 'AdguardSvc.exe' in result.stdout:
                self.log("⚠ Adguard process found - may cause problems")
            else:
                self.log("✓ Adguard check passed")
            
            self.log("Diagnostics completed")
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def check_updates(self):
        """Проверяет обновления zapret"""
        self.log("=== Check Updates ===")
        if self.parent_manager:
            self.parent_manager.check_update()
            self.log("Update check initiated - see main window logs")
        else:
            self.log("Error: parent manager not available")
        self.log("")
    
    def toggle_check_updates(self):
        """Переключает автоматическую проверку обновлений"""
        self.log("=== Toggle Check Updates ===")
        try:
            check_updates_flag = os.path.join(ROOT_DIR, "utils", "check_updates.enabled")
            if os.path.exists(check_updates_flag):
                os.remove(check_updates_flag)
                self.log("Check updates DISABLED")
            else:
                utils_dir = os.path.join(ROOT_DIR, "utils")
                if not os.path.exists(utils_dir):
                    os.makedirs(utils_dir)
                with open(check_updates_flag, 'w') as f:
                    f.write("ENABLED")
                self.log("Check updates ENABLED")
            self.update_statuses()
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def toggle_game_filter(self):
        """Переключает игровой фильтр"""
        self.log("=== Toggle Game Filter ===")
        try:
            game_filter_flag = os.path.join(ROOT_DIR, "utils", "game_filter.enabled")
            if os.path.exists(game_filter_flag):
                os.remove(game_filter_flag)
                self.log("Game filter DISABLED")
            else:
                utils_dir = os.path.join(ROOT_DIR, "utils")
                if not os.path.exists(utils_dir):
                    os.makedirs(utils_dir)
                with open(game_filter_flag, 'w') as f:
                    f.write("ENABLED")
                self.log("Game filter ENABLED")
            self.update_statuses()
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def toggle_ipset(self):
        """Переключает режим ipset"""
        self.log("=== Toggle ipset ===")
        try:
            list_file = os.path.join(ROOT_DIR, "lists", "ipset-all.txt")
            backup_file = f"{list_file}.backup"
            
            # Определяем текущий статус
            if os.path.exists(list_file):
                with open(list_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        current_status = "any"
                    elif content == "203.0.113.113/32":
                        current_status = "none"
                    else:
                        current_status = "loaded"
            else:
                current_status = "any"
            
            if current_status == "loaded":
                # Переключаем на none
                if not os.path.exists(backup_file):
                    shutil.copy2(list_file, backup_file)
                with open(list_file, 'w', encoding='utf-8') as f:
                    f.write("203.0.113.113/32")
                self.log("ipset switched to 'none' mode")
            elif current_status == "none":
                # Переключаем на any
                with open(list_file, 'w', encoding='utf-8') as f:
                    f.write("")
                self.log("ipset switched to 'any' mode")
            else:  # any
                # Переключаем на loaded
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, list_file)
                    self.log("ipset switched to 'loaded' mode")
                else:
                    self.log("Error: no backup to restore. Update list first.")
            self.update_statuses()
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def update_ipset_list(self):
        """Обновляет список ipset"""
        self.log("=== Update ipset list ===")
        if self.parent_manager:
            # Запускаем обновление в отдельном потоке
            threading.Thread(target=self.parent_manager.update_ipset, daemon=True).start()
            self.log("ipset update initiated - see main window logs")
        else:
            self.log("Error: parent manager not available")
        self.log("")
    
    def update_hosts(self):
        """Обновляет hosts файл"""
        self.log("=== Update hosts file ===")
        try:
            hosts_file = os.path.join(os.environ['SystemRoot'], 'System32', 'drivers', 'etc', 'hosts')
            hosts_url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/hosts"
            
            response = requests.get(hosts_url, timeout=10)
            response.raise_for_status()
            
            temp_file = os.path.join(os.environ['TEMP'], 'zapret_hosts.txt')
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            self.log(f"Hosts file downloaded to: {temp_file}")
            self.log("Please manually copy content to your hosts file:")
            self.log(hosts_file)
            self.log("Opening files...")
            
            subprocess.Popen(['notepad.exe', temp_file])
            subprocess.Popen(['explorer.exe', '/select,', hosts_file])
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")
    
    def run_tests(self):
        """Запускает тесты"""
        self.log("=== Run Tests ===")
        try:
            test_script = os.path.join(ROOT_DIR, "utils", "test zapret.ps1")
            if os.path.exists(test_script):
                subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', 
                                '-File', test_script])
                self.log("Test script launched in PowerShell window")
            else:
                self.log("Test script not found")
        except Exception as e:
            self.log(f"Error: {str(e)}")
        self.log("")

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
        
        # Сначала обновление ipset, затем проверка обновлений (если включена), затем запуск zapret
        self._user_stopped = False
        self._zapret_auto_restart_pending = False
        self.update_ipset_on_start()
        QTimer.singleShot(800, self._maybe_auto_start_telegram_proxy)

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
        painter.setBrush(QColor(0x19, 0x19, 0x19))  
        
        
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20, 20)
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

    def stop_all_zapret_processes_and_services(self):
        """Останавливает все процессы и сервисы zapret для обновления (как в service.bat :service_remove)"""
        try:
            self.update_log.emit("Stopping all zapret processes and services...")
            
            # Останавливаем основной процесс, если запущен
            if self.process and self.process.poll() is None:
                try:
                    self.stop_process()
                except:
                    pass
            
            # Останавливаем все процессы winws.exe
            stopped_winws = False
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'] and 'winws.exe' in proc.info['name'].lower():
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        stopped_winws = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if stopped_winws:
                self.update_log.emit("Stopped winws.exe processes")
            
            # Останавливаем сервис zapret
            try:
                result = subprocess.run(['sc', 'query', 'zapret'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    subprocess.run(['net', 'stop', 'zapret'], 
                                 capture_output=True, timeout=10)
                    subprocess.run(['sc', 'delete', 'zapret'], 
                                 capture_output=True, timeout=5)
                    self.update_log.emit("Stopped and removed zapret service")
            except:
                pass
            
            # Останавливаем сервисы WinDivert
            for service_name in ['WinDivert', 'WinDivert14']:
                try:
                    result = subprocess.run(['sc', 'query', service_name], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        subprocess.run(['net', 'stop', service_name], 
                                     capture_output=True, timeout=10)
                        subprocess.run(['sc', 'delete', service_name], 
                                     capture_output=True, timeout=5)
                        self.update_log.emit(f"Stopped and removed {service_name} service")
                except:
                    pass
            
            # Даем время на завершение процессов
            time.sleep(2)
            
            self.update_log.emit("All zapret processes and services stopped")
            return True
            
        except Exception as e:
            self.update_log.emit(f"Error stopping zapret processes: {str(e)}")
            return False

    def init_ui(self):
        self.setWindowTitle("FAmerica")
        self.setFixedSize(620, 460)
        
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: transparent; border-radius: 20px;")
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.sidebar = LeftSidebar(self)
        main_layout.addWidget(self.sidebar)
        
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #191919;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)
        
        self.stacked = QStackedWidget()
        self.stacked.setStyleSheet("background-color: #191919;")
        
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #191919;
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
        top_section.setStyleSheet("QWidget { background-color: #252525; border-radius: 10px; }")
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(6)
        

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
        
        middle_section = QWidget()
        middle_section.setStyleSheet("QWidget { background-color: #252525; border-radius: 10px; }")
        middle_layout = QVBoxLayout(middle_section)
        middle_layout.setContentsMargins(10, 10, 10, 10)
        middle_layout.setSpacing(8)
        
        bat_layout = QHBoxLayout()
        bat_layout.addWidget(QLabel("Select BAT file:"))
        self.bat_combo = BatFileComboBox(self)
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
        
        checkboxes_layout = QHBoxLayout()
        checkboxes_layout.setSpacing(10)
        checkboxes_layout.addStretch()
        self.apply_defaults_btn = QPushButton("Fix Discord")
        self.apply_defaults_btn.setStyleSheet("""
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E5E5E;
                color: #4AFF95;
            }
            QPushButton:pressed {
                background-color: #1F1F1F;
            }
        """)
        self.apply_defaults_btn.setToolTip("Enable game filter and set ipset to 'none' mode")
        self.apply_defaults_btn.clicked.connect(self.apply_default_settings)
        checkboxes_layout.addWidget(self.apply_defaults_btn)
        btn_style = """
            QPushButton {
                background-color: #464646;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5E5E5E; color: #4AFF95; }
            QPushButton:pressed { background-color: #1F1F1F; color: #4AFF95; }
            QPushButton:disabled { background-color: #1A1A1A; color: #666666; }
        """
        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self.update_app)
        self.update_btn.setStyleSheet(btn_style)
        checkboxes_layout.addWidget(self.update_btn)
        middle_layout.addLayout(checkboxes_layout)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        self.start_btn = QPushButton("START")
        self.start_btn.clicked.connect(self.start_process)
        self.start_btn.setStyleSheet(btn_style)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.clicked.connect(self.stop_process)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(btn_style)
        buttons_layout.addWidget(self.start_btn, 1)
        buttons_layout.addWidget(self.stop_btn, 1)
        middle_layout.addLayout(buttons_layout)
        
        zapret_page = QWidget()
        zapret_page.setStyleSheet("background-color: #191919;")
        zapret_page_layout = QVBoxLayout(zapret_page)
        zapret_page_layout.setContentsMargins(0, 0, 0, 0)
        zapret_page_layout.setSpacing(8)
        zapret_page_layout.addWidget(top_section)
        zapret_page_layout.addWidget(middle_section, 1)
        self.stacked.addWidget(zapret_page)
        
        telegram_page = QWidget()
        telegram_page.setStyleSheet("background-color: #191919;")
        telegram_layout = QVBoxLayout(telegram_page)
        telegram_layout.setSpacing(10)
        tg_title = QLabel("Telegram Fix")
        tg_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 12px;")
        telegram_layout.addWidget(tg_title)
        port_row = QHBoxLayout()
        self.telegram_proxy_port_spinbox = QSpinBox()
        self.telegram_proxy_port_spinbox.setRange(1, 65535)
        self.telegram_proxy_port_spinbox.setValue(1080)
        self.telegram_proxy_port_spinbox.setStyleSheet("background-color: #252525; color: #FFF; border: none; border-radius: 5px; padding: 6px; min-width: 80px;")
        port_row.addWidget(self.telegram_proxy_port_spinbox)
        port_row.addStretch()
        telegram_layout.addLayout(port_row)
        self.telegram_proxy_dc_edit = QPlainTextEdit()
        self.telegram_proxy_dc_edit.setPlaceholderText("2:149.154.167.220\n4:149.154.167.220")
        self.telegram_proxy_dc_edit.setMaximumHeight(70)
        self.telegram_proxy_dc_edit.setStyleSheet("background-color: #252525; color: #FFF; border: none; border-radius: 5px; padding: 6px; font-size: 11px;")
        self.telegram_proxy_dc_edit.setPlainText("2:149.154.167.220\n4:149.154.167.220")
        telegram_layout.addWidget(self.telegram_proxy_dc_edit)
        btn_row = QHBoxLayout()
        btn_style_tg = "QPushButton { background-color: #464646; color: #FFF; border: none; border-radius: 5px; padding: 8px 14px; } QPushButton:hover { background-color: #5E5E5E; color: #4AFF95; } QPushButton:disabled { background-color: #333; color: #666; }"
        self.telegram_proxy_start_btn = QPushButton("Запустить прокси")
        self.telegram_proxy_start_btn.setStyleSheet(btn_style_tg)
        self.telegram_proxy_start_btn.clicked.connect(self._telegram_proxy_start)
        self.telegram_proxy_stop_btn = QPushButton("Остановить прокси")
        self.telegram_proxy_stop_btn.setStyleSheet(btn_style_tg)
        self.telegram_proxy_stop_btn.setEnabled(False)
        self.telegram_proxy_stop_btn.clicked.connect(self._telegram_proxy_stop)
        btn_row.addWidget(self.telegram_proxy_start_btn, 1)
        btn_row.addWidget(self.telegram_proxy_stop_btn, 1)
        telegram_layout.addLayout(btn_row)
        telegram_layout.addStretch()
        if not TG_PROXY_AVAILABLE:
            tg_warn = QLabel("Установите cryptography: pip install cryptography")
            tg_warn.setStyleSheet("color: #cc6600; font-size: 11px;")
            telegram_layout.addWidget(tg_warn)
            self.telegram_proxy_start_btn.setEnabled(False)
        telegram_layout.addStretch()
        self.telegram_proxy_thread = None
        self.stacked.addWidget(telegram_page)
        
        settings_page = QWidget()
        settings_page.setStyleSheet("background-color: #191919;")
        settings_page_layout = QVBoxLayout(settings_page)
        settings_page_layout.setSpacing(12)
        self.auto_update_cb = CustomCheckBox("Auto-update on start")
        self.auto_update_cb.setChecked(True)
        self.auto_update_cb.stateChanged.connect(self.on_auto_update_change)
        settings_page_layout.addWidget(self.auto_update_cb)
        self.auto_start_cb = CustomCheckBox("Auto-start with Windows")
        self.auto_start_cb.stateChanged.connect(self.on_auto_start_change)
        settings_page_layout.addWidget(self.auto_start_cb)
        self.telegram_proxy_autostart_cb = CustomCheckBox("Auto-start telegram fix (SOCKS5 WebSocket Proxy)")
        self.telegram_proxy_autostart_cb.setChecked(True)
        self.telegram_proxy_autostart_cb.stateChanged.connect(self._on_telegram_proxy_autostart_change)
        settings_page_layout.addWidget(self.telegram_proxy_autostart_cb)
        settings_page_layout.addSpacing(8)
        open_settings_btn = QPushButton("Open Service Settings")
        open_settings_btn.setStyleSheet("""
            QPushButton { background-color: #464646; color: #FFF; border: none; border-radius: 5px; padding: 10px 15px; }
            QPushButton:hover { background-color: #5E5E5E; color: #4AFF95; }
        """)
        open_settings_btn.clicked.connect(self._open_settings_window)
        settings_page_layout.addWidget(open_settings_btn)
        settings_credits = QLabel("v0.5 created by skrudw")
        settings_credits.setStyleSheet("color: #888888; font-size: 10px;")
        settings_page_layout.addWidget(settings_credits)
        settings_page_layout.addStretch()
        self.stacked.addWidget(settings_page)
        
        right_layout.addWidget(self.stacked)
        
        bottom_section = QWidget()
        bottom_section.setStyleSheet("QWidget { background-color: #252525; border-radius: 10px; }")
        bottom_layout = QVBoxLayout(bottom_section)
        bottom_layout.setContentsMargins(8, 6, 8, 8)
        bottom_layout.setSpacing(4)
        bottom_layout.addWidget(QLabel("Logs:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(140)
        self.log_text.setStyleSheet("background-color: #1A1A1A; color: #FFFFFF; border: none; border-radius: 8px; padding: 8px; font-size: 11px;")
        bottom_layout.addWidget(self.log_text, 1)
        right_layout.addWidget(bottom_section)
        
        main_layout.addWidget(right_widget)
        
        self.sidebar.tab_zapret.clicked.connect(lambda: self._set_page(0))
        self.sidebar.tab_telegram.clicked.connect(lambda: self._set_page(1))
        self.sidebar.tab_settings.clicked.connect(lambda: self._set_page(2))

    def _set_page(self, index):
        self.stacked.setCurrentIndex(index)
        self.sidebar.tab_zapret.setChecked(index == 0)
        self.sidebar.tab_telegram.setChecked(index == 1)
        self.sidebar.tab_settings.setChecked(index == 2)

    def _open_settings_window(self):
        if not hasattr(self, 'settings_window') or self.settings_window is None:
            self.settings_window = SettingsWindow(self)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _telegram_proxy_start(self):
        if not TG_PROXY_AVAILABLE or self.telegram_proxy_thread and self.telegram_proxy_thread.isRunning():
            return
        port = self.telegram_proxy_port_spinbox.value()
        lines = [l.strip() for l in self.telegram_proxy_dc_edit.toPlainText().strip().splitlines() if l.strip()]
        if not lines:
            QMessageBox.warning(self, "Telegram Fix", "Укажите хотя бы один DC:IP (например 2:149.154.167.220)")
            return
        try:
            dc_opt = tg_ws_proxy.parse_dc_ip_list(lines)
        except ValueError as e:
            QMessageBox.warning(self, "Telegram Fix", f"Ошибка в DC:IP: {e}")
            return
        self.save_config()
        self.telegram_proxy_thread = TelegramProxyThread(port, dc_opt, "127.0.0.1", self)
        self.telegram_proxy_thread.error_signal.connect(self._telegram_proxy_error)
        self.telegram_proxy_thread.finished.connect(self._telegram_proxy_finished)
        self.update_log.emit(f"Telegram proxy: starting on 127.0.0.1:{port}")
        self.telegram_proxy_thread.start()
        self.telegram_proxy_start_btn.setEnabled(False)
        self.telegram_proxy_stop_btn.setEnabled(True)
        QTimer.singleShot(1500, lambda p=port: self.update_log.emit(f"Telegram proxy: started on 127.0.0.1:{p}") if (getattr(self, 'telegram_proxy_thread', None) and self.telegram_proxy_thread.isRunning()) else None)
        QTimer.singleShot(2000, lambda p=port: self._telegram_proxy_open_in_tg_auto(p))

    def _telegram_proxy_stop(self):
        if self.telegram_proxy_thread and self.telegram_proxy_thread.isRunning():
            self.telegram_proxy_thread.request_stop()
            self.update_log.emit("Telegram proxy: stopping...")

    def _telegram_proxy_open_in_tg_auto(self, port):
        try:
            webbrowser.open(f"tg://socks?server=127.0.0.1&port={port}")
        except Exception:
            pass

    def _telegram_proxy_finished(self):
        self.telegram_proxy_start_btn.setEnabled(TG_PROXY_AVAILABLE)
        self.telegram_proxy_stop_btn.setEnabled(False)
        self.update_log.emit("Telegram proxy: stopped")
        self.telegram_proxy_thread = None

    def _telegram_proxy_error(self, msg):
        self._telegram_proxy_finished()
        self.update_log.emit(f"Telegram proxy error: {msg}")
        QMessageBox.warning(self, "Telegram Fix", f"Ошибка прокси: {msg}")

    def _on_telegram_proxy_autostart_change(self, state):
        self.save_config()

    def _maybe_auto_start_telegram_proxy(self):
        if not getattr(self, 'telegram_proxy_autostart_cb', None) or not self.telegram_proxy_autostart_cb.isChecked():
            return
        if not TG_PROXY_AVAILABLE or (self.telegram_proxy_thread and self.telegram_proxy_thread.isRunning()):
            return
        self._telegram_proxy_start()

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

    def apply_default_settings(self):
        """Применяет настройки по умолчанию: включает game filter и устанавливает ipset в режим 'none'"""
        try:
            # Включаем game filter
            utils_dir = os.path.join(ROOT_DIR, "utils")
            if not os.path.exists(utils_dir):
                os.makedirs(utils_dir)
            
            game_filter_file = os.path.join(utils_dir, "game_filter.enabled")
            with open(game_filter_file, 'w', encoding='utf-8') as f:
                f.write("ENABLED")
            self.update_log.emit("Game filter enabled")
            
            # Устанавливаем ipset в режим 'none'
            lists_dir = os.path.join(ROOT_DIR, "lists")
            if not os.path.exists(lists_dir):
                os.makedirs(lists_dir)
            
            list_file = os.path.join(lists_dir, "ipset-all.txt")
            backup_file = f"{list_file}.backup"
            
            # Сохраняем backup текущего файла, если он существует и не пустой
            if os.path.exists(list_file):
                try:
                    with open(list_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content and content != "203.0.113.113/32":
                            # Сохраняем backup только если файл не пустой и не в режиме "none"
                            with open(backup_file, 'w', encoding='utf-8') as bf:
                                bf.write(content)
                except:
                    pass
            
            # Устанавливаем ipset в режим "none"
            with open(list_file, 'w', encoding='utf-8') as f:
                f.write("203.0.113.113/32")
            
            self.update_log.emit("ipset switched to 'none' mode")
            self.update_log.emit("Default settings applied successfully")
            
            # Обновляем статусы в окне настроек, если оно открыто
            if hasattr(self, 'settings_window') and self.settings_window:
                self.settings_window.update_statuses()
        except Exception as e:
            self.update_log.emit(f"Error applying default settings: {str(e)}")

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

    def update_ipset_on_start(self):
        """Выполняет обновление ipset при запуске; по завершении запускает проверку обновлений или zapret."""
        bin_dir = os.path.join(ROOT_DIR, "bin")
        if not os.path.exists(bin_dir):
            self.update_log.emit("Zapret files not installed (bin folder not found), skipping ipset update")
            self._on_ipset_update_done()
            return
        self.update_log.emit("Starting ipset update...")
        self._ipset_thread = IpsetUpdateThread(self)
        self._ipset_thread.log_msg.connect(self.update_log.emit)
        self._ipset_thread.finished.connect(self._on_ipset_update_done)
        self._ipset_thread.start()

    def _on_ipset_update_done(self):
        """После завершения обновления ipset — проверка обновлений или сразу запуск zapret."""
        if self.auto_update_cb.isChecked():
            self.auto_update_on_start()
        else:
            QTimer.singleShot(1000, self.start_process)

    def update_ipset(self):
        """Обновляет ipset список, реализуя логику :ipset_update из service.bat"""
        try:
            # Путь к файлу списка ipset (аналогично service.bat)
            lists_dir = os.path.join(ROOT_DIR, "lists")
            if not os.path.exists(lists_dir):
                os.makedirs(lists_dir)
            
            list_file = os.path.join(lists_dir, "ipset-all.txt")
            url = "https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/refs/heads/main/.service/ipset-service.txt"
            
            self.update_log.emit(f"Updating ipset-all from {url}...")
            
            # Загружаем файл через requests (как в batch используется curl или PowerShell)
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                # Сохраняем backup текущего файла перед обновлением, если он существует и не пустой
                backup_file = f"{list_file}.backup"
                old_content = None
                if os.path.exists(list_file):
                    try:
                        with open(list_file, 'r', encoding='utf-8') as f:
                            old_content = f.read().strip()
                            # Сохраняем backup только если файл не пустой и не в режиме "none"
                            if old_content and old_content != "203.0.113.113/32":
                                with open(backup_file, 'w', encoding='utf-8') as bf:
                                    bf.write(old_content)
                    except:
                        pass
                
                # Сохраняем загруженный файл как backup (новый список)
                if not old_content or old_content == "203.0.113.113/32" or not os.path.exists(backup_file):
                    # Если backup не существует или файл был в режиме "none", сохраняем новый список как backup
                    with open(backup_file, 'w', encoding='utf-8') as bf:
                        bf.write(response.text)
                
                # Сохраняем обновленный список
                with open(list_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                self.update_log.emit(f"Successfully updated ipset list (backup saved, {len(response.text)} bytes)")
                self.update_log.emit("ipset update finished")
            except requests.exceptions.RequestException as e:
                self.update_log.emit(f"Error downloading ipset list: {str(e)}")
                self.update_log.emit("ipset update failed")
        except Exception as e:
            self.update_log.emit(f"Error during ipset update: {str(e)}")

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
                    if hasattr(self, 'telegram_proxy_port_spinbox'):
                        self.telegram_proxy_port_spinbox.setValue(config.get('telegram_proxy_port', 1080))
                    if hasattr(self, 'telegram_proxy_dc_edit'):
                        dc_ip = config.get('telegram_proxy_dc_ip', ["2:149.154.167.220", "4:149.154.167.220"])
                        self.telegram_proxy_dc_edit.setPlainText("\n".join(dc_ip) if isinstance(dc_ip, list) else str(dc_ip))
                    if hasattr(self, 'telegram_proxy_autostart_cb'):
                        self.telegram_proxy_autostart_cb.setChecked(config.get('telegram_proxy_autostart', True))
                    
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
        if hasattr(self, 'telegram_proxy_port_spinbox'):
            config['telegram_proxy_port'] = self.telegram_proxy_port_spinbox.value()
        if hasattr(self, 'telegram_proxy_dc_edit'):
            dc_text = self.telegram_proxy_dc_edit.toPlainText().strip()
            config['telegram_proxy_dc_ip'] = [l.strip() for l in dc_text.splitlines() if l.strip()] or ["2:149.154.167.220", "4:149.154.167.220"]
        if hasattr(self, 'telegram_proxy_autostart_cb'):
            config['telegram_proxy_autostart'] = self.telegram_proxy_autostart_cb.isChecked()
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f)

    def check_update(self):
        """Проверяет обновления в отдельном потоке"""
        self.update_checker_thread = UpdateCheckerThread(self.repo_url, self.current_version)
        self.update_checker_thread.update_available.connect(self.on_update_available)
        self.update_checker_thread.error.connect(self._on_update_check_error)
        self.update_checker_thread.start()

    @pyqtSlot(str)
    def _on_update_check_error(self, error_msg):
        """При ошибке проверки обновлений всё равно запускаем zapret (например, нет интернета)."""
        self.update_log.emit(error_msg)
        if self.auto_update_cb.isChecked():
            self.update_log.emit("Starting zapret anyway (update check failed).")
            QTimer.singleShot(1000, self.start_process)

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
        # Останавливаем все процессы zapret перед обновлением
        success = self.stop_all_zapret_processes_and_services()
        if not success:
            # Если не удалось остановить процессы, предлагаем перезагрузку
            reply = QMessageBox.question(
                self, 
                'Не удалось остановить процессы',
                'Некоторые процессы zapret не удалось остановить.\n\n'
                'Возможны два варианта:\n'
                '1. Попробовать продолжить (может возникнуть ошибка)\n'
                '2. Перезагрузить компьютер для завершения обновления\n\n'
                'Хотите перезагрузить компьютер сейчас?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    subprocess.run(['shutdown', '/r', '/t', '10', '/c', 'Перезагрузка для обновления zapret'], check=True)
                    self.update_log.emit("Компьютер будет перезагружен через 10 секунд для обновления zapret")
                    QMessageBox.information(self, 'Перезагрузка', 'Компьютер будет перезагружен через 10 секунд.')
                except Exception as e:
                    self.update_log.emit(f"Ошибка при попытке перезагрузки: {str(e)}")
                    QMessageBox.warning(self, 'Ошибка', 'Не удалось инициировать перезагрузку. Попробуйте вручную.')
                return
        
        self.set_progress_visible.emit(True)
        self.update_progress.emit(0)
        
        self.download_thread = DownloadThread(url, self)
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
        self._user_stopped = False

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
        self._user_stopped = True
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

    def _do_auto_restart(self):
        if getattr(self, '_zapret_auto_restart_pending', False):
            self._zapret_auto_restart_pending = False
            self.update_log.emit("Restarting zapret after unexpected exit...")
            self.start_process()

    def monitor_process(self):
        try:
            self.process.wait()
            code = self.process.returncode if self.process else None
            self.update_status.emit("Not running")
            self.update_log.emit("Process finished")
            self.set_buttons_enabled.emit(True, False)
            if code != 0 and not getattr(self, '_user_stopped', True) and not getattr(self, '_zapret_auto_restart_pending', False):
                self._zapret_auto_restart_pending = True
                QTimer.singleShot(5000, self._do_auto_restart)
        except Exception as e:
            self.update_log.emit(f"Error monitoring process: {str(e)}")

if __name__ == "__main__":
    download_icons_if_missing()
    check_for_update()
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