# gui.py
# -*- coding: utf-8 -*-
import sys
import os
import traceback
from pathlib import Path
from typing import List, Dict

# ---------------------------------------------------------
# [CRITICAL FIX] macOS Bundle Startup Fixes
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    # This block only runs when packaged as an App/Exe
    bundle_dir = sys._MEIPASS
    
    # 1. Fix missing Z3 libraries (DYLD_LIBRARY_PATH)
    # Allows the app to find libz3.dylib bundled inside it
    current_dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
    os.environ['DYLD_LIBRARY_PATH'] = f"{bundle_dir}{os.pathsep}{current_dyld}"
    os.environ['PATH'] = f"{bundle_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    
    # 2. Fix "Print Crash" (Stdout/Stderr Redirection) - SILENT MODE
    # Redirect output to "null" to prevent crash without creating a file on Desktop
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
    except Exception:
        pass

# ---------------------------------------------------------
# NORMAL IMPORTS
# ---------------------------------------------------------
# PyQt6
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor, QBrush
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QTableWidgetItem, QHeaderView,
    QFileDialog
)

# Fluent Widgets
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, PrimaryPushButton, PushButton,
    TextEdit, InfoBar, InfoBarPosition, setTheme, Theme, setThemeColor,
    FluentIcon, CardWidget, IconWidget, BodyLabel, CaptionLabel,
    SwitchButton, TableWidget, TitleLabel, SubtitleLabel 
)

# ---------------------------------------------------------
# IMPORT USER FUNCTIONS (Updated Path)
# ---------------------------------------------------------
try:
    # Importing from the 'Code.SMT4ModPlant' package structure as requested
    from Code.SMT4ModPlant.GeneralRecipeParser import parse_general_recipe
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
    from Code.SMT4ModPlant.SMT4ModPlant_main import run_optimization
except ImportError as e:
    print("Import Error: Could not load modules.")
    print("Please ensure the directory structure is as follows:")
    print("  gui.py")
    print("  Code/")
    print("    SMT4ModPlant/")
    print("      __init__.py (Must exist)")
    print("      GeneralRecipeParser.py")
    print("      AASxmlCapabilityParser.py")
    print("      SMT4ModPlant_main.py")
    print(f"Specific Error: {e}")
    sys.exit(1)


# ---------------------------------------------------------
# WORKER THREAD
# ---------------------------------------------------------
class SMTWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, recipe_path, resource_dir):
        super().__init__()
        self.recipe_path = recipe_path
        self.resource_dir = resource_dir

    def run(self):
        try:
            self.log_signal.emit(f"Parsing Recipe: {self.recipe_path}")
            recipe_data = parse_general_recipe(self.recipe_path)
            self.progress_signal.emit(20, 100)

            self.log_signal.emit(f"Scanning resource directory: {self.resource_dir}")
            
            # Logic: Look for both .xml and .aasx files
            # The backend automatically distinguishes between them.
            resource_files = [f for f in os.listdir(self.resource_dir) if f.lower().endswith('.xml') or f.lower().endswith('.aasx')]
            
            if not resource_files:
                raise FileNotFoundError("No .xml or .aasx files found in the selected directory.")

            all_capabilities = {}
            total_files = len(resource_files)
            
            for idx, filename in enumerate(resource_files):
                full_path = os.path.join(self.resource_dir, filename)
                res_name = Path(filename).stem
                self.log_signal.emit(f"Parsing resource file: {filename}")
                
                try:
                    # The robust parser automatically detects XML vs AASX based on extension or content
                    # If XML -> Reads directly. If AASX -> Unzips and reads XML.
                    caps = parse_capabilities_robust(full_path)
                    if caps: # Ensure valid capabilities were found
                        key_name = f"resource: {res_name}" 
                        all_capabilities[key_name] = caps
                    else:
                        self.log_signal.emit(f"Warning: No capabilities found in {filename}")
                        
                except Exception as parse_err:
                    self.log_signal.emit(f"Warning: Failed to parse {filename}: {parse_err}")

                progress = 20 + int((idx + 1) / total_files * 40)
                self.progress_signal.emit(progress, 100)

            self.log_signal.emit(f"Loaded {len(all_capabilities)} valid resources.")

            if not all_capabilities:
                raise ValueError("No valid resources loaded. Cannot proceed.")

            self.log_signal.emit("Starting SMT Optimization (Z3)...")
            
            # Call with generate_json=True to save all solutions
            results = run_optimization(recipe_data, all_capabilities, log_callback=self.log_signal.emit, generate_json=True)
            
            self.progress_signal.emit(100, 100)
            self.finished_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(str(e))
            self.log_signal.emit(traceback.format_exc())


# ---------------------------------------------------------
# GUI PAGES
# ---------------------------------------------------------

class LogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log_page")
        layout = QVBoxLayout(self)
        self.title = SubtitleLabel("Execution Log", self)
        self.log_edit = TextEdit(self)
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.title)
        layout.addWidget(self.log_edit, 1)

    def append_log(self, msg: str):
        self.log_edit.append(msg)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

class ResultsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("results_page")
        layout = QVBoxLayout(self)
        self.title = SubtitleLabel("Matching Results (All Solutions)", self)
        
        self.table = TableWidget(self)
        # Increased column count to 6 to include Solution ID
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Sol ID", "Step ID", "Description", "Assigned Resource", "Capabilities", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setWordWrap(False)
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Capabilities column stretch
        
        layout.addWidget(self.title)
        layout.addWidget(self.table, 1)

    def update_table(self, data: List[Dict]):
        self.table.setRowCount(len(data))
        for r, row_data in enumerate(data):
            
            # Check if this is a separator row (empty dict)
            if not row_data:
                # Fill the row with empty, disabled items to create a visual break
                for c in range(6):
                    item = QTableWidgetItem("")
                    # Set background color slightly different to indicate separator (optional, works better in light mode)
                    # item.setBackground(QBrush(QColor(50, 50, 50))) 
                    item.setFlags(Qt.ItemFlag.NoItemFlags) # Disable selection
                    self.table.setItem(r, c, item)
                continue

            # Regular Data Row
            # Col 0: Solution ID
            self.table.setItem(r, 0, QTableWidgetItem(str(row_data.get('solution_id', ''))))
            # Col 1: Step ID
            self.table.setItem(r, 1, QTableWidgetItem(str(row_data['step_id'])))
            # Col 2: Description
            self.table.setItem(r, 2, QTableWidgetItem(str(row_data['description'])))
            # Col 3: Resource
            self.table.setItem(r, 3, QTableWidgetItem(str(row_data['resource'])))
            # Col 4: Capabilities
            self.table.setItem(r, 4, QTableWidgetItem(str(row_data['capabilities'])))
            
            # Col 5: Status (Green)
            status_item = QTableWidgetItem(str(row_data['status']))
            status_item.setForeground(QColor("#28a745")) 
            self.table.setItem(r, 5, status_item)

class HomePage(QWidget):
    def __init__(self, log_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self.log_callback = log_callback
        self.recipe_path = ""
        self.resource_dir = ""
        
        # Apply Theme Color (IAT Blue style)
        setThemeColor("#00629B")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = TitleLabel("SMT4ModPlant Orchestrator", self)
        desc = CaptionLabel("Resource matching tool based on General Recipe and AAS Capabilities.", self)
        desc.setStyleSheet("color: #666;") 
        
        layout.addWidget(title)
        layout.addWidget(desc)

        # Card 1: Recipe
        self.card_recipe = CardWidget(self)
        l1 = QHBoxLayout(self.card_recipe)
        
        # Using standard DOCUMENT icon
        icon1 = IconWidget(FluentIcon.DOCUMENT, self)
        
        v1 = QVBoxLayout()
        self.lbl_recipe = BodyLabel("General Recipe XML", self)
        self.lbl_recipe_val = CaptionLabel("No file selected", self)
        v1.addWidget(self.lbl_recipe)
        v1.addWidget(self.lbl_recipe_val)
        btn1 = PushButton("Select File", self)
        btn1.clicked.connect(self.select_recipe)
        l1.addWidget(icon1)
        l1.addLayout(v1, 1)
        l1.addWidget(btn1)
        layout.addWidget(self.card_recipe)

        # Card 2: Resources
        self.card_res = CardWidget(self)
        l2 = QHBoxLayout(self.card_res)
        
        # Using standard FOLDER icon
        icon2 = IconWidget(FluentIcon.FOLDER, self)
        
        v2 = QVBoxLayout()
        
        # Label updated to indicate support for both XML and AASX
        self.lbl_res = BodyLabel("Resources Directory (XML/AASX)", self)
        self.lbl_res_val = CaptionLabel("No folder selected", self)
        v2.addWidget(self.lbl_res)
        v2.addWidget(self.lbl_res_val)
        btn2 = PushButton("Select Folder", self)
        btn2.clicked.connect(self.select_folder)
        l2.addWidget(icon2)
        l2.addLayout(v2, 1)
        l2.addWidget(btn2)
        layout.addWidget(self.card_res)

        # Actions
        self.btn_run = PrimaryPushButton("Start Calculation", self)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)

        # Progress
        self.pbar = QProgressBar(self)
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)
        
        layout.addStretch()

    def select_recipe(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Recipe XML", os.getcwd(), "XML Files (*.xml)")
        if f:
            self.recipe_path = f
            self.lbl_recipe_val.setText(os.path.basename(f))
            self.check_ready()

    def select_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Resources Folder", os.getcwd())
        if d:
            self.resource_dir = d
            self.lbl_res_val.setText(d)
            self.check_ready()

    def check_ready(self):
        if self.recipe_path and self.resource_dir:
            self.btn_run.setEnabled(True)

    def run_process(self):
        self.btn_run.setEnabled(False)
        self.log_callback("Starting Process...")
        self.worker = SMTWorker(self.recipe_path, self.resource_dir)
        self.worker.log_signal.connect(self.log_callback)
        self.worker.progress_signal.connect(lambda c, t: (self.pbar.setMaximum(t), self.pbar.setValue(c)))
        self.worker.error_signal.connect(lambda e: InfoBar.error(title="Error", content=e, parent=self.window()))
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, results):
        self.btn_run.setEnabled(True)
        main = self.window()
        if isinstance(main, MainWindow):
            main.results_page.update_table(results)
            main.switchTo(main.results_page)
            InfoBar.success(title="Completed", content=f"Calculation finished. Found valid solutions.", parent=main, position=InfoBarPosition.TOP_RIGHT)

# ---------------------------------------------------------
# SETTINGS PAGE
# ---------------------------------------------------------
class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        self.title = TitleLabel("Settings", self)
        layout.addWidget(self.title)
        
        # Theme Toggle
        self.card_theme = CardWidget(self)
        l_theme = QHBoxLayout(self.card_theme)
        icon_theme = IconWidget(FluentIcon.BRUSH, self)
        lbl_theme = BodyLabel("Dark Mode", self)
        self.switch_theme = SwitchButton(self)
        
        # Set default to True for Dark Mode
        self.switch_theme.setChecked(True) 
        
        self.switch_theme.checkedChanged.connect(self.toggle_theme)
        
        l_theme.addWidget(icon_theme)
        l_theme.addWidget(lbl_theme)
        l_theme.addStretch(1)
        l_theme.addWidget(self.switch_theme)
        layout.addWidget(self.card_theme)
        
        layout.addStretch()

    def toggle_theme(self, checked):
        if checked:
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)

# ---------------------------------------------------------
# MAIN WINDOW
# ---------------------------------------------------------

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMT4ModPlant GUI Orchestrator")
        
        # Set default theme to DARK
        setTheme(Theme.DARK)
        
        self.resize(1000, 700)
        
        # Center Window
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width()//2 - self.width()//2, geo.height()//2 - self.height()//2)
        
        # Pages
        self.home_page = HomePage(self.log_callback_shim, self)
        self.results_page = ResultsPage(self)
        self.log_page = LogPage(self)
        self.settings_page = SettingsPage(self)
        
        # Navigation
        self.addSubInterface(self.home_page, FluentIcon.HOME, "Home", NavigationItemPosition.TOP)
        self.addSubInterface(self.results_page, FluentIcon.ACCEPT, "Results", NavigationItemPosition.TOP)
        self.addSubInterface(self.log_page, FluentIcon.DOCUMENT, "Log", NavigationItemPosition.TOP)
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "Settings", NavigationItemPosition.BOTTOM)
        
        self.switchTo(self.home_page)

    def log_callback_shim(self, msg):
        self.log_page.append_log(msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())