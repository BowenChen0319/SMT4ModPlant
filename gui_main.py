# gui_main.py
# -*- coding: utf-8 -*-
import sys
import os
# ... (Imports and Bundle Fixes stay same) ...

# PyQt6 Imports
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme
)

try:
    from Code.GUI.Home import HomePage
    from Code.GUI.Logs import LogPage
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMT4ModPlant GUI Orchestrator")
        setTheme(Theme.DARK)
        self.resize(1200, 800) # Initial window size
        
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width()//2 - self.width()//2, geo.height()//2 - self.height()//2)
        
        self.log_page = LogPage(self)
        
        self.home_page = HomePage(self.log_callback_shim, self)
        
        # Add Navigation
        self.addSubInterface(self.home_page, FluentIcon.HOME, "Home", NavigationItemPosition.TOP)
        # self.addSubInterface(self.results_page, FluentIcon.ACCEPT, "Results", NavigationItemPosition.TOP) <-- [删除]
        self.addSubInterface(self.log_page, FluentIcon.DOCUMENT, "Log", NavigationItemPosition.TOP)
        
        self.switchTo(self.home_page)

    def log_callback_shim(self, msg):
        self.log_page.append_log(msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    # w.show()
    w.showMaximized()  
    sys.exit(app.exec())