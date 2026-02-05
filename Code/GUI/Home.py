# Code/GUI/Home.py
import os
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QProgressBar, QFrame, QSizePolicy, QScrollArea, QApplication
)
from qfluentwidgets import (
    CardWidget, IconWidget, BodyLabel, CaptionLabel, 
    PrimaryPushButton, PushButton, CheckBox,
    TitleLabel, SubtitleLabel, FluentIcon, InfoBar, InfoBarPosition, setThemeColor,
    FluentWindow, SwitchButton, DoubleSpinBox, ScrollArea
)

from Code.GUI.Workers import SMTWorker
from Code.GUI.Results import ResultsWidget

class HomePage(QWidget):
    def __init__(self, log_callback, parent=None):
        super().__init__(parent)
        """Main landing page that gathers user input and triggers SMT/OPT runs."""
        self.setObjectName("home_page")
        self.log_callback = log_callback
        
        # --- Variables ---
        self.recipe_path = ""
        self.resource_dir = ""
        self.default_export_path = os.path.normpath(os.path.expanduser("~/Downloads"))
        self.current_export_path = self.default_export_path
        self.mode_index = 0
        self.prev_vals = {}
        self.anim = None 
        self.split_anim = None
        
        setThemeColor("#00629B")
        
        self.init_ui()
        
    def init_ui(self):
        """Build the overall two-panel layout and wire initial UI components."""
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Left Panel (Config)
        self.left_scroll = ScrollArea(self)
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setStyleSheet("QScrollArea {border: none; background-color: transparent;}")
        
        self.left_container = QWidget()
        self.left_container.setStyleSheet(".QWidget{background-color: transparent;}")
        
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(30, 30, 30, 30)
        self.left_layout.setSpacing(15)
        
        self._init_left_panel_content()
        
        self.left_scroll.setWidget(self.left_container)
        self.main_layout.addWidget(self.left_scroll, 1)

        # Right Panel (Results)
        self.right_container = QWidget(self)
        self.right_container.setFixedWidth(0) 
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 30, 30, 30)
        
        self.results_widget = ResultsWidget(self)
        self.right_layout.addWidget(self.results_widget)
        
        self.main_layout.addWidget(self.right_container, 0)

    def _init_left_panel_content(self):
        """Create the configuration cards on the left side (file pickers, mode, weights)."""
        layout = self.left_layout
        
        # Header
        header_layout = QHBoxLayout()
        v_title = QVBoxLayout()
        title = TitleLabel("SMT4ModPlant Orchestrator", self)
        desc = CaptionLabel("Resource matching tool based on General Recipe and AAS Capabilities.", self)
        desc.setStyleSheet("color: #999;") 
        v_title.addWidget(title)
        v_title.addWidget(desc)
        header_layout.addLayout(v_title)
        header_layout.addStretch(1)
        layout.addLayout(header_layout)

        # 1. Recipe
        self.card_recipe = CardWidget(self)
        l1 = QHBoxLayout(self.card_recipe)
        l1.setContentsMargins(20, 20, 20, 20) 
        icon1 = IconWidget(FluentIcon.DOCUMENT, self)
        v1 = QVBoxLayout()
        self.lbl_recipe = SubtitleLabel("General Recipe XML", self)
        self.lbl_recipe_val = CaptionLabel("No file selected", self)
        v1.addWidget(self.lbl_recipe)
        v1.addWidget(self.lbl_recipe_val)
        btn1 = PushButton("Select File", self)
        btn1.clicked.connect(self.select_recipe)
        l1.addWidget(icon1)
        l1.addLayout(v1, 1)
        l1.addWidget(btn1)
        layout.addWidget(self.card_recipe)

        # 2. Resource
        self.card_res = CardWidget(self)
        l2 = QHBoxLayout(self.card_res)
        l2.setContentsMargins(20, 20, 20, 20)
        icon2 = IconWidget(FluentIcon.FOLDER, self)
        v2 = QVBoxLayout()
        self.lbl_res = SubtitleLabel("Resources Directory (XML/AASX/JSON)", self)
        self.lbl_res_val = CaptionLabel("No folder selected", self)
        v2.addWidget(self.lbl_res)
        v2.addWidget(self.lbl_res_val)
        btn2 = PushButton("Select Folder", self)
        btn2.clicked.connect(self.select_folder)
        l2.addWidget(icon2)
        l2.addLayout(v2, 1)
        l2.addWidget(btn2)
        layout.addWidget(self.card_res)

        # 3. Export Directory
        self.card_export = CardWidget(self)
        l_export = QHBoxLayout(self.card_export)
        l_export.setContentsMargins(20, 20, 20, 20)
        icon_exp = IconWidget(FluentIcon.SAVE, self)
        v_exp_text = QVBoxLayout()
        lbl_exp_title = SubtitleLabel("Export Directory", self)
        self.lbl_exp_path = CaptionLabel(self.default_export_path, self)
        self.lbl_exp_path.setWordWrap(False) 
        v_exp_text.addWidget(lbl_exp_title)
        v_exp_text.addWidget(self.lbl_exp_path)
        
        self.lbl_switch_status = BodyLabel("Default (Downloads)", self)
        self.lbl_switch_status.setStyleSheet("color: #666;")
        self.switch_custom_path = SwitchButton(self)
        self.switch_custom_path.setOnText("")
        self.switch_custom_path.setOffText("")
        self.switch_custom_path.checkedChanged.connect(self.toggle_path_mode)
        self.btn_browse_path = PushButton("Browse", self)
        self.btn_browse_path.clicked.connect(self.browse_path)
        self.btn_browse_path.setEnabled(False) 
        
        l_export.addWidget(icon_exp)
        l_export.addLayout(v_exp_text, 1) 
        l_export.addStretch(0) 
        l_export.addWidget(self.lbl_switch_status) 
        l_export.addSpacing(10)
        l_export.addWidget(self.switch_custom_path) 
        l_export.addSpacing(20)
        l_export.addWidget(self.btn_browse_path) 
        layout.addWidget(self.card_export)

        # 4. Mode
        self.card_mode = CardWidget(self)
        l_mode = QHBoxLayout(self.card_mode)
        l_mode.setContentsMargins(20, 20, 20, 20)
        icon_mode = IconWidget(FluentIcon.SPEED_HIGH, self)
        lbl_mode = SubtitleLabel("Solution Type", self)
        self.cb_smt = CheckBox("SMT (Get All Solution)", self)
        self.cb_opt = CheckBox("OPT (Get Best One from Multi-Solution)", self)
        self.cb_smt.setChecked(True)
        self.cb_opt.setChecked(False)
        self.cb_smt.stateChanged.connect(self.on_smt_checked)
        self.cb_opt.stateChanged.connect(self.on_opt_checked)
        l_mode.addWidget(icon_mode)
        l_mode.addWidget(lbl_mode)
        l_mode.addStretch(1)
        l_mode.addWidget(self.cb_smt)
        l_mode.addSpacing(20)
        l_mode.addWidget(self.cb_opt)
        layout.addWidget(self.card_mode)

        # 5. Weights
        self.card_weights = CardWidget(self)
        l_weights = QVBoxLayout(self.card_weights)
        l_weights.setContentsMargins(20, 20, 20, 20)
        l_weights.setSpacing(10)
        w_header = QHBoxLayout()
        w_header.setContentsMargins(0,0,0,0)
        w_title = SubtitleLabel("Optimization Weights (Sum = 1.0)", self)
        w_header.addWidget(w_title)
        w_header.addStretch(1)
        l_weights.addLayout(w_header)
        
        def create_weight_row(label, default_val):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
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
        
        self.prev_vals = {self.spin_energy: 0.4, self.spin_use: 0.3, self.spin_co2: 0.3}
        self.spin_energy.valueChanged.connect(lambda v: self.balance_weights(self.spin_energy, v))
        self.spin_use.valueChanged.connect(lambda v: self.balance_weights(self.spin_use, v))
        self.spin_co2.valueChanged.connect(lambda v: self.balance_weights(self.spin_co2, v))
        self.card_weights.setMaximumHeight(0)
        self.card_weights.setVisible(False)

        # Button & Progress
        self.btn_run = PrimaryPushButton("Start Calculation in SMT Mode", self)
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.run_process)
        layout.addWidget(self.btn_run)
        
        self.pbar = QProgressBar(self)
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)
        
        layout.addStretch()
        self.update_run_button_style(0)

    # -----------------------------------------------------
    # Window Resize & Animation Logic
    # -----------------------------------------------------
    def toggle_weights_animation(self, show):
        """
        Animate the weights card and resize the window only when showing it.

        Args:
            show: True to expand the weights card; False to collapse.
        """
        if show and self.card_weights.isVisible() and self.card_weights.maximumHeight() > 0: return
        if not show and not self.card_weights.isVisible(): return

        # 1. Measure target height
        self.card_weights.setMaximumHeight(16777215) 
        self.card_weights.adjustSize()
        target_height = self.card_weights.sizeHint().height()

        # 2. [New] Resize Window Logic
        if show:
            win = self.window()
            if win:
                current_h = win.height()
                new_h = current_h + target_height + 20 
                screen = QApplication.primaryScreen().availableGeometry()
                if new_h < screen.height():
                    win.resize(win.width(), new_h)

        # 3. Start Animation
        self.anim = QPropertyAnimation(self.card_weights, b"maximumHeight")
        self.anim.setDuration(300) 
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic) 
        if show:
            self.card_weights.setVisible(True)
            self.anim.setStartValue(0)
            self.anim.setEndValue(target_height)
        else:
            self.anim.setStartValue(target_height)
            self.anim.setEndValue(0)
            self.anim.finished.connect(lambda: self.card_weights.setVisible(False))
        self.anim.start()

    def toggle_results_panel(self, show=True):
        """Slide the results panel open/closed by animating its width."""
        parent_width = self.width()
        target_width = parent_width // 2 if show else 0
        start_width = self.right_container.width()
        
        if start_width == target_width:
            return

        self.split_anim = QPropertyAnimation(self.right_container, b"minimumWidth")
        self.split_anim.setDuration(500) 
        self.split_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.split_anim.setStartValue(start_width)
        self.split_anim.setEndValue(target_width)
        
        self.split_anim_max = QPropertyAnimation(self.right_container, b"maximumWidth")
        self.split_anim_max.setDuration(500)
        self.split_anim_max.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.split_anim_max.setStartValue(start_width)
        self.split_anim_max.setEndValue(target_width)
        
        self.group = QParallelAnimationGroup()
        self.group.addAnimation(self.split_anim)
        self.group.addAnimation(self.split_anim_max)
        
        self.group.start()

    # -----------------------------------------------------
    # Logic: Mode Selection
    # -----------------------------------------------------
    def on_smt_checked(self, state):
        """Keep SMT checkbox mutually exclusive and update UI for SMT mode."""
        if state == Qt.CheckState.Checked.value: 
            self.cb_opt.blockSignals(True)
            self.cb_opt.setChecked(False)
            self.cb_opt.blockSignals(False)
            self.mode_index = 0
            self.toggle_weights_animation(False)
            self.btn_run.setText("Start Calculation in SMT Mode")
            self.update_run_button_style(0)
            self.notify_color_change("#107C10")
        else:
            if not self.cb_opt.isChecked(): self.cb_smt.setChecked(True)

    def on_opt_checked(self, state):
        """Keep OPT checkbox mutually exclusive and update UI for OPT mode."""
        if state == Qt.CheckState.Checked.value: 
            self.cb_smt.blockSignals(True)
            self.cb_smt.setChecked(False)
            self.cb_smt.blockSignals(False)
            self.mode_index = 1
            self.toggle_weights_animation(True)
            self.btn_run.setText("Start Calculation in OPT Mode")
            self.update_run_button_style(1)
            self.notify_color_change("#FF8C00")
        else:
            if not self.cb_smt.isChecked(): self.cb_opt.setChecked(True)

    def update_run_button_style(self, mode_idx):
        """Apply consistent theming to the primary run button based on mode."""
        color_hex = "#107C10" if mode_idx == 0 else "#FF8C00"
        btn_style = f"""
            PrimaryPushButton {{ background-color: {color_hex}; border: 1px solid {color_hex}; border-radius: 6px; color: white; height: 40px; font-size: 16px; font-weight: bold; font-family: 'Segoe UI', sans-serif; }}
            PrimaryPushButton:hover {{ background-color: {color_hex}; border: 1px solid {color_hex}; }}
            PrimaryPushButton:pressed {{ background-color: {color_hex}; opacity: 0.8; }}
            PrimaryPushButton:disabled {{ background-color: {color_hex}; opacity: 0.5; border: 1px solid {color_hex}; color: rgba(255, 255, 255, 0.8); }}
        """
        self.btn_run.setStyleSheet(btn_style)

    def notify_color_change(self, color_hex):
        """Propagate accent color changes to the results export button."""
        self.results_widget.set_export_button_color(color_hex)

    def balance_weights(self, source_spin, new_val):
        """Adjust the other two weights evenly so the sum remains 1.0."""
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

    def get_weights(self):
        """Return the tuple of (energy, use, CO2) weights."""
        return (self.spin_energy.value(), self.spin_use.value(), self.spin_co2.value())

    def toggle_path_mode(self, checked):
        """Enable/disable custom export path selection."""
        self.btn_browse_path.setEnabled(checked)
        if checked:
            self.lbl_switch_status.setText("Custom Path")
        else:
            self.lbl_switch_status.setText("Default (Downloads)")
            self.current_export_path = self.default_export_path
            self.lbl_exp_path.setText(self.current_export_path)

    def browse_path(self):
        """Open a directory chooser for the export location."""
        start_dir = self.current_export_path if os.path.exists(self.current_export_path) else os.getcwd()
        d = QFileDialog.getExistingDirectory(self, "Select Export Directory", start_dir)
        if d:
            norm_d = os.path.normpath(d)
            self.current_export_path = norm_d
            self.lbl_exp_path.setText(norm_d)

    def get_export_path(self):
        """Return the currently selected export directory."""
        return self.lbl_exp_path.text()

    def select_recipe(self):
        """Prompt for a General Recipe XML file and update state."""
        f, _ = QFileDialog.getOpenFileName(self, "Select Recipe XML", os.getcwd(), "XML Files (*.xml)")
        if f:
            self.recipe_path = os.path.normpath(f)
            self.lbl_recipe_val.setText(os.path.basename(self.recipe_path))
            self.check_ready()

    def select_folder(self):
        """Prompt for the resources directory and update state."""
        d = QFileDialog.getExistingDirectory(self, "Select Resources Folder", os.getcwd())
        if d:
            self.resource_dir = os.path.normpath(d)
            self.lbl_res_val.setText(self.resource_dir)
            self.check_ready()

    def check_ready(self):
        """Enable Run only when both recipe and resources are selected."""
        if self.recipe_path and self.resource_dir:
            self.btn_run.setEnabled(True)

    def run_process(self):
        """Instantiate the worker thread and kick off SMT/OPT processing."""
        self.btn_run.setEnabled(False)
        self.log_callback("Starting Process...")
        weights = self.get_weights()
        self.worker = SMTWorker(self.recipe_path, self.resource_dir, self.mode_index, weights)
        self.worker.log_signal.connect(self.log_callback)
        self.worker.progress_signal.connect(lambda c, t: (self.pbar.setMaximum(t), self.pbar.setValue(c)))
        self.worker.error_signal.connect(self.handle_error)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, results, context_data):
        """Handle successful completion: re-enable UI, notify, and show results."""
        self.btn_run.setEnabled(True)
        InfoBar.success(title="Completed", content=f"Calculation finished.", parent=self, position=InfoBarPosition.TOP_RIGHT)
        self.results_widget.set_data(results, context_data)
        self.toggle_results_panel(True)

    def handle_error(self, err_msg):
        """
        Show error InfoBar and reset UI so user can retry without restarting the app.
        """
        self.pbar.setMaximum(100)
        self.pbar.setValue(0)
        self.btn_run.setEnabled(True)
        InfoBar.error(title="Error", content=err_msg, parent=self, position=InfoBarPosition.TOP_RIGHT)

    def resizeEvent(self, event):
        """Keep the split layout responsive when the window size changes."""
        if self.right_container.width() > 0:
             self.right_container.setFixedWidth(self.width() // 2)
        super().resizeEvent(event)
