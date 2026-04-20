# gui_main.py
# -*- coding: utf-8 -*-
import sys
import os
# ... (Imports and Bundle Fixes stay same) ...

# % pyinstaller --noconsole --name="PlantConfigurator" --clean \                                          
#  --collect-all qfluentwidgets \
#  --collect-all z3 \
#  --icon="Others/logo.icns" \
#  gui_main.py


# PyQt6 Imports
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme,
    InfoBarPosition
)
from Code.GUI.Notifications import SafeInfoBar as InfoBar

try:
    from Code.GUI.Home import HomePage
    from Code.GUI.Logs import LogPage
    from Code.GUI.RecipeValidator import RecipeValidatorPage
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)

class MainWindow(FluentWindow):
    """Top-level window hosting navigation, the Home page, and log view."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plant Configurator and Master Recipe Generator")
        setTheme(Theme.DARK)
        self.resize(1200, 800) # Initial window size
        
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width()//2 - self.width()//2, geo.height()//2 - self.height()//2)
        
        self.log_page = LogPage(self)
        self.recipe_validator_page = RecipeValidatorPage(self)
        
        self.home_page = HomePage(self.log_callback_shim, self)
        
        # Add Navigation
        self.addSubInterface(self.home_page, FluentIcon.HOME, "Home", NavigationItemPosition.TOP)
        self.addSubInterface(self.recipe_validator_page, FluentIcon.ACCEPT, "Recipe Validator", NavigationItemPosition.TOP)
        self.addSubInterface(self.log_page, FluentIcon.DOCUMENT, "Log", NavigationItemPosition.TOP)
        
        self.switchTo(self.home_page)

    def get_export_path(self):
        """Return the active export path selected in the current UI."""
        if hasattr(self, "home_page") and hasattr(self.home_page, "get_export_path"):
            try:
                return self.home_page.get_export_path()
            except Exception:
                pass

        if hasattr(self, "settings_page") and hasattr(self.settings_page, "get_export_path"):
            try:
                return self.settings_page.get_export_path()
            except Exception:
                pass

        return ""

    def log_callback_shim(self, msg):
        """Bridge the worker log signal into the log page widget."""
        try:
            self.log_page.append_log(msg)
        except Exception:
            pass

    def closeEvent(self, event):
        """Prevent teardown while the worker thread is still running."""
        if hasattr(self, "home_page") and hasattr(self.home_page, "is_worker_running"):
            try:
                if self.home_page.is_worker_running():
                    InfoBar.warning(
                        title="Calculation Running",
                        content="Please wait until the current calculation finishes before closing the app.",
                        parent=self,
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=4000,
                    )
                    event.ignore()
                    return
            except Exception:
                pass

        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    # w.show()
    w.showMaximized()  
    sys.exit(app.exec())
