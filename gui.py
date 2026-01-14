# gui.py
# -*- coding: utf-8 -*-
import sys
import os
import traceback
from pathlib import Path
from typing import List, Dict

# ---------------------------------------------------------
# [CRITICAL FIX] Bundle Startup Fixes
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    current_dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
    os.environ['DYLD_LIBRARY_PATH'] = f"{bundle_dir}{os.pathsep}{current_dyld}"
    os.environ['PATH'] = f"{bundle_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
    except Exception:
        pass

# ---------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor, QBrush, QFont
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QTableWidgetItem, QHeaderView,
    QFileDialog, QSlider, QFrame
)

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, PrimaryPushButton, PushButton,
    TextEdit, InfoBar, InfoBarPosition, setTheme, Theme, setThemeColor,
    FluentIcon, CardWidget, IconWidget, BodyLabel, CaptionLabel,
    SwitchButton, TableWidget, TitleLabel, SubtitleLabel, Slider,
    DoubleSpinBox
)

# ---------------------------------------------------------
# CUSTOM UI COMPONENTS
# ---------------------------------------------------------

class ZoneSlider(Slider):
    """
    A custom slider that defines specific click zones:
    - 0%  - 35%: Index 0 (Fast)
    - 35% - 65%: Index 1 (Pro)
    - 65% - 100%: Index 2 (Ultra)
    """
    def mousePressEvent(self, event):
        if self.orientation() == Qt.Orientation.Horizontal:
            # Calculate click ratio (0.0 to 1.0)
            ratio = event.pos().x() / self.width()
            
            val = 1 # Default Pro
            
            if ratio < 0.35:
                val = 0 # Fast (Left 35%)
            elif ratio > 0.65:
                val = 2 # Ultra (Right 35%)
            else:
                val = 1 # Pro (Middle 30%)
            
            # Set value and trigger signals
            self.setValue(val)
            event.accept()
            
            # If you want to allow dragging after click, we could call super(),
            # but for a mode switcher, 'jump to spot' is usually better.
            # super().mousePressEvent(event) 
        else:
            super().mousePressEvent(event)


# ---------------------------------------------------------
# IMPORT USER FUNCTIONS
# ---------------------------------------------------------
try:
    from Code.SMT4ModPlant.GeneralRecipeParser import parse_general_recipe
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
    from Code.SMT4ModPlant.SMT4ModPlant_main import run_optimization
    from Code.Optimizer.Optimization import SolutionOptimizer
except ImportError as e:
    print("Import Error: Could not load modules.")
    print("Ensure Code/SMT4ModPlant and Code/Optimizer directories exist.")
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

    def __init__(self, recipe_path, resource_dir, mode_index, weights):
        super().__init__()
        self.recipe_path = recipe_path
        self.resource_dir = resource_dir
        self.mode_index = mode_index # 0:Fast, 1:Pro, 2:Ultra
        self.weights = weights # (energy, use, co2)

    def run(self):
        try:
            # 1. Parsing
            self.log_signal.emit(f"Parsing Recipe: {self.recipe_path}")
            recipe_data = parse_general_recipe(self.recipe_path)
            self.progress_signal.emit(10, 100)

            self.log_signal.emit(f"Scanning resource directory: {self.resource_dir}")
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
                    caps = parse_capabilities_robust(full_path)
                    if caps:
                        key_name = f"resource: {res_name}" 
                        all_capabilities[key_name] = caps
                except Exception as parse_err:
                    self.log_signal.emit(f"Warning: Failed to parse {filename}: {parse_err}")

                progress = 10 + int((idx + 1) / total_files * 20)
                self.progress_signal.emit(progress, 100)

            self.log_signal.emit(f"Loaded {len(all_capabilities)} valid resources.")
            if not all_capabilities: raise ValueError("No valid resources loaded.")

            # 2. SMT Logic Configuration
            find_all = (self.mode_index >= 1) # Pro or Ultra
            is_ultra = (self.mode_index == 2)
            
            mode_names = ['Fast', 'Pro', 'Ultra']
            self.log_signal.emit(f"Starting SMT Logic (Mode: {mode_names[self.mode_index]})...")
            
            # SMT run
            gui_results, json_solutions = run_optimization(
                recipe_data, 
                all_capabilities, 
                log_callback=self.log_signal.emit, 
                generate_json=is_ultra, 
                find_all_solutions=find_all
            )
            
            self.progress_signal.emit(60, 100)

            # 3. Ultra Optimization Logic
            if is_ultra and json_solutions:
                self.log_signal.emit("Ultra Mode: Calculating costs and finding optimal solution...")
                
                optimizer = SolutionOptimizer()
                # Set weights from settings
                optimizer.set_weights(*self.weights)
                # Load resource costs from the directory
                optimizer.load_resource_costs_from_dir(self.resource_dir)
                
                # Optimize from memory
                evaluated_solutions = optimizer.optimize_solutions_from_memory(json_solutions)
                
                # Merge scores into gui_results
                sorted_gui_results = []
                
                # evaluated_solutions is sorted by score (best first)
                for eval_sol in evaluated_solutions:
                    sol_id = eval_sol['solution_id']
                    
                    # Find all rows in gui_results matching this sol_id
                    rows = [r for r in gui_results if r.get('solution_id') == sol_id]
                    
                    if sorted_gui_results: sorted_gui_results.append({})
                    
                    for row in rows:
                        row['composite_score'] = eval_sol['composite_score']
                        row['energy_cost'] = eval_sol['total_energy_cost']
                        row['use_cost'] = eval_sol['total_use_cost']
                        row['co2_footprint'] = eval_sol['total_co2_footprint']
                        sorted_gui_results.append(row)
                
                gui_results = sorted_gui_results
                if evaluated_solutions:
                    self.log_signal.emit(f"Optimization complete. Best Solution ID: {evaluated_solutions[0]['solution_id']}")

            self.progress_signal.emit(100, 100)
            self.finished_signal.emit(gui_results)

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
        self.title = SubtitleLabel("Calculation Results", self)
        
        self.table = TableWidget(self)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setWordWrap(True)
        
        layout.addWidget(self.title)
        layout.addWidget(self.table, 1)

    def update_table(self, data: List[Dict]):
        # Determine if we have score data (Ultra mode)
        has_score = False
        if data and len(data) > 0:
            for row in data:
                if row: 
                    if 'composite_score' in row: 
                        has_score = True
                    break
        
        # Filter logic: Remove solutions with Score 0 if in Ultra mode
        if has_score:
            filtered_data = []
            temp_block = []
            
            for row in data:
                if not row: # Separator found
                    if temp_block:
                        score = temp_block[0].get('composite_score', 0)
                        if score > 0:
                            if filtered_data: filtered_data.append({}) 
                            filtered_data.extend(temp_block)
                        temp_block = []
                else:
                    temp_block.append(row)
            
            if temp_block:
                score = temp_block[0].get('composite_score', 0)
                if score > 0:
                    if filtered_data: filtered_data.append({})
                    filtered_data.extend(temp_block)
            
            data = filtered_data
            
        
        # Configure Columns
        if has_score:
            headers = ["Sol ID", "Score", "Step", "Description", "Resource", "Capabilities", "Energy", "Use", "CO2"]
            self.table.setColumnCount(9)
        else:
            headers = ["Sol ID", "Step", "Description", "Resource", "Capabilities", "Status"]
            self.table.setColumnCount(6)
            
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        cap_col_idx = 5 if has_score else 4
        self.table.horizontalHeader().setSectionResizeMode(cap_col_idx, QHeaderView.ResizeMode.Stretch)

        self.table.setRowCount(len(data))
        
        for r, row_data in enumerate(data):
            if not row_data:
                for c in range(self.table.columnCount()):
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.table.setItem(r, c, item)
                continue

            if has_score:
                self.table.setItem(r, 0, QTableWidgetItem(str(row_data.get('solution_id', ''))))
                self.table.setItem(r, 1, QTableWidgetItem(f"{row_data.get('composite_score', 0):.2f}"))
                self.table.setItem(r, 2, QTableWidgetItem(str(row_data['step_id'])))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['description'])))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data['resource'])))
                self.table.setItem(r, 5, QTableWidgetItem(str(row_data['capabilities'])))
                self.table.setItem(r, 6, QTableWidgetItem(f"{row_data.get('energy_cost', 0):.1f}"))
                self.table.setItem(r, 7, QTableWidgetItem(f"{row_data.get('use_cost', 0):.1f}"))
                self.table.setItem(r, 8, QTableWidgetItem(f"{row_data.get('co2_footprint', 0):.1f}"))
            else:
                self.table.setItem(r, 0, QTableWidgetItem(str(row_data.get('solution_id', ''))))
                self.table.setItem(r, 1, QTableWidgetItem(str(row_data['step_id'])))
                self.table.setItem(r, 2, QTableWidgetItem(str(row_data['description'])))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['resource'])))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data['capabilities'])))
                status_item = QTableWidgetItem(str(row_data['status']))
                status_item.setForeground(QColor("#28a745"))
                self.table.setItem(r, 5, status_item)
        
        self.table.resizeRowsToContents()

class HomePage(QWidget):
    def __init__(self, log_callback, settings_page, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self.log_callback = log_callback
        self.settings_page = settings_page
        self.recipe_path = ""
        self.resource_dir = ""
        
        setThemeColor("#00629B")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = TitleLabel("SMT4ModPlant Orchestrator", self)
        desc = CaptionLabel("Resource matching tool based on General Recipe and AAS Capabilities.", self)
        desc.setStyleSheet("color: #666;") 
        layout.addWidget(title)
        layout.addWidget(desc)

        # File Inputs
        self.card_recipe = CardWidget(self)
        l1 = QHBoxLayout(self.card_recipe)
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

        self.card_res = CardWidget(self)
        l2 = QHBoxLayout(self.card_res)
        icon2 = IconWidget(FluentIcon.FOLDER, self)
        v2 = QVBoxLayout()
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

        # --- Mode Slider Section ---
        self.card_opts = CardWidget(self)
        l_opts = QHBoxLayout(self.card_opts)
        icon_opts = IconWidget(FluentIcon.SPEED_HIGH, self)
        
        v_opts = QVBoxLayout()
        self.lbl_opts = BodyLabel("Optimization Mode", self)
        
        # 1. Container for Slider and Ticks
        v_slider_container = QVBoxLayout()
        v_slider_container.setSpacing(5)
        
        # 2. The Custom Slider (ZoneSlider)
        # [MODIFIED] Using ZoneSlider instead of Slider
        self.slider_mode = ZoneSlider(Qt.Orientation.Horizontal, self)
        self.slider_mode.setRange(0, 2)
        self.slider_mode.setPageStep(1)
        self.slider_mode.setSingleStep(1)
        self.slider_mode.setValue(0) # Default: Fast
        self.slider_mode.setFixedWidth(200)
        self.slider_mode.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_mode.setTickInterval(1)
        self.slider_mode.valueChanged.connect(self.update_ui_state)
        
        v_slider_container.addWidget(self.slider_mode)
        
        # 3. The Labels Below (Fast - Pro - Ultra)
        h_labels = QHBoxLayout()
        h_labels.setContentsMargins(0,0,0,0)
        
        lbl_fast = CaptionLabel("Fast", self)
        lbl_pro = CaptionLabel("Pro", self)
        lbl_ultra = CaptionLabel("Ultra", self)
        
        font = QFont()
        font.setPointSize(13) # Increased size
        lbl_fast.setFont(font)
        lbl_pro.setFont(font)
        lbl_ultra.setFont(font)
        
        # Alignment
        lbl_fast.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lbl_pro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ultra.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        h_labels.addWidget(lbl_fast)
        h_labels.addWidget(lbl_pro)
        h_labels.addWidget(lbl_ultra)
        
        v_slider_container.addLayout(h_labels)
        
        self.lbl_opts_desc = CaptionLabel("Fast (1 Sol)", self)
        v_opts.addWidget(self.lbl_opts)
        v_opts.addWidget(self.lbl_opts_desc)
        
        l_opts.addWidget(icon_opts)
        l_opts.addLayout(v_opts, 1) 
        l_opts.addLayout(v_slider_container) 
        
        layout.addWidget(self.card_opts)

        # Big Button
        self.btn_run = PrimaryPushButton("Start Calculation in Fast Mode", self)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)

        # Progress Bar (Standard)
        self.pbar = QProgressBar(self)
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)
        
        layout.addStretch()
        
        # Initialize UI state (Default: Fast/Green)
        self.update_ui_state(0)

    def update_ui_state(self, val):
        """Update colors and text based on slider value immediately"""
        modes = ["Fast", "Pro", "Ultra"]
        mode_text = modes[val]
        
        # Update Settings Visibility
        if self.settings_page:
            self.settings_page.set_weights_visible(val == 2)

        # Define colors (Green, Blue, Orange)
        if val == 0: # Fast - Green
            color_hex = "#107C10" 
            desc = "Fast (Single Solution)"
        elif val == 1: # Pro - Blue (IAT style)
            color_hex = "#00629B"
            desc = "Pro (All Valid Solutions)"
        else: # Ultra - Orange
            color_hex = "#FF8C00" 
            desc = "Ultra (Cost Optimization)"

        self.lbl_opts_desc.setText(desc)
        self.btn_run.setText(f"Start Calculation in {mode_text} Mode")
        
        # Button Styling
        btn_style = f"""
            PrimaryPushButton {{
                background-color: {color_hex};
                border: 1px solid {color_hex};
                border-radius: 6px;
                color: white;
                height: 40px;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }}
            PrimaryPushButton:hover {{
                background-color: {color_hex}; 
                border: 1px solid {color_hex};
            }}
            PrimaryPushButton:pressed {{
                background-color: {color_hex};
                opacity: 0.8;
            }}
            PrimaryPushButton:disabled {{
                background-color: {color_hex};
                opacity: 0.5; 
                border: 1px solid {color_hex};
                color: rgba(255, 255, 255, 0.8);
            }}
        """
        self.btn_run.setStyleSheet(btn_style)
        
        # Slider Styling
        slider_style = f"""
            Slider::groove:horizontal {{
                height: 4px; 
                background: #cccccc;
                border-radius: 2px;
            }}
            Slider::handle:horizontal {{
                background: {color_hex};
                border: 2px solid {color_hex};
                width: 18px;
                height: 18px;
                border-radius: 10px;
                margin: -7px 0;
            }}
            Slider::sub-page:horizontal {{
                background: {color_hex};
                border-radius: 2px;
            }}
        """
        self.slider_mode.setStyleSheet(slider_style)

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
        
        mode = self.slider_mode.value()
        weights = self.settings_page.get_weights()
        
        self.worker = SMTWorker(self.recipe_path, self.resource_dir, mode, weights)
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
            InfoBar.success(title="Completed", content=f"Calculation finished.", parent=main, position=InfoBarPosition.TOP_RIGHT)

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
        self.switch_theme.setChecked(True) 
        self.switch_theme.checkedChanged.connect(self.toggle_theme)
        l_theme.addWidget(icon_theme)
        l_theme.addWidget(lbl_theme)
        l_theme.addStretch(1)
        l_theme.addWidget(self.switch_theme)
        layout.addWidget(self.card_theme)
        
        # Weights (Initially Hidden)
        self.card_weights = CardWidget(self)
        l_weights = QVBoxLayout(self.card_weights)
        l_weights.setContentsMargins(20, 20, 20, 20)
        
        w_title = SubtitleLabel("Optimization Weights (Sum = 1.0)", self)
        l_weights.addWidget(w_title)
        
        def create_weight_row(label, default_val):
            row = QHBoxLayout()
            lbl = BodyLabel(label, self)
            spin = DoubleSpinBox(self)
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.1)
            spin.setValue(default_val)
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(spin)
            return row, spin
            
        r1, self.spin_energy = create_weight_row("Energy Cost Weight", 0.4)
        r2, self.spin_use = create_weight_row("Use Cost Weight", 0.3)
        r3, self.spin_co2 = create_weight_row("CO2 Footprint Weight", 0.3)
        
        l_weights.addLayout(r1)
        l_weights.addLayout(r2)
        l_weights.addLayout(r3)
        layout.addWidget(self.card_weights)
        
        self.card_weights.setVisible(False)
        
        self.spin_energy.valueChanged.connect(lambda v: self.balance_weights(self.spin_energy, v))
        self.spin_use.valueChanged.connect(lambda v: self.balance_weights(self.spin_use, v))
        self.spin_co2.valueChanged.connect(lambda v: self.balance_weights(self.spin_co2, v))
        
        self.prev_vals = {
            self.spin_energy: 0.4,
            self.spin_use: 0.3,
            self.spin_co2: 0.3
        }
        
        layout.addStretch()

    def set_weights_visible(self, visible: bool):
        self.card_weights.setVisible(visible)

    def balance_weights(self, source_spin, new_val):
        old_val = self.prev_vals[source_spin]
        delta = new_val - old_val
        self.prev_vals[source_spin] = new_val
        
        if abs(delta) < 0.0001: return
        
        others = [s for s in [self.spin_energy, self.spin_use, self.spin_co2] if s != source_spin]
        for s in others: s.blockSignals(True)
        adjustment = delta / 2.0
        
        for s in others:
            curr = s.value()
            s.setValue(max(0.0, min(1.0, curr - adjustment)))
            self.prev_vals[s] = s.value()
            
        for s in others: s.blockSignals(False)

    def toggle_theme(self, checked):
        if checked: setTheme(Theme.DARK)
        else: setTheme(Theme.LIGHT)
        
    def get_weights(self):
        return (self.spin_energy.value(), self.spin_use.value(), self.spin_co2.value())

# ---------------------------------------------------------
# MAIN WINDOW
# ---------------------------------------------------------

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMT4ModPlant GUI Orchestrator")
        setTheme(Theme.DARK)
        self.resize(1100, 750)
        
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width()//2 - self.width()//2, geo.height()//2 - self.height()//2)
        
        self.settings_page = SettingsPage(self)
        self.log_page = LogPage(self)
        self.results_page = ResultsPage(self)
        self.home_page = HomePage(self.log_callback_shim, self.settings_page, self)
        
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