# Code/GUI/Home.py
import os
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QProgressBar
)
from qfluentwidgets import (
    CardWidget, IconWidget, BodyLabel, CaptionLabel, 
    PrimaryPushButton, PushButton, CheckBox,
    TitleLabel, SubtitleLabel, FluentIcon, InfoBar, InfoBarPosition, setThemeColor,
    FluentWindow, SwitchButton, DoubleSpinBox
)

from Code.GUI.Workers import SMTWorker

class HomePage(QWidget):
    def __init__(self, log_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self.log_callback = log_callback
        
        # 初始化变量
        self.recipe_path = ""
        self.resource_dir = ""
        
        # [修改] 使用 os.path.normpath 确保默认路径在不同系统(Win/Mac)下显示正确的斜杠
        self.default_export_path = os.path.normpath(os.path.expanduser("~/Downloads"))
        self.current_export_path = self.default_export_path
        
        self.mode_index = 0 # 0=SMT(Fast), 2=OPT(Ultra)
        
        # 权重相关变量
        self.prev_vals = {}
        
        # 动画对象占位
        self.anim = None
        
        setThemeColor("#00629B")
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15) 

        # --- Header ---
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

        # =================================================
        # 1. General Recipe XML
        # =================================================
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

        # =================================================
        # 2. Resources Directory
        # =================================================
        self.card_res = CardWidget(self)
        l2 = QHBoxLayout(self.card_res)
        l2.setContentsMargins(20, 20, 20, 20)
        
        icon2 = IconWidget(FluentIcon.FOLDER, self)
        v2 = QVBoxLayout()
        self.lbl_res = SubtitleLabel("Resources Directory (XML/AASX)", self)
        self.lbl_res_val = CaptionLabel("No folder selected", self)
        v2.addWidget(self.lbl_res)
        v2.addWidget(self.lbl_res_val)
        
        btn2 = PushButton("Select Folder", self)
        btn2.clicked.connect(self.select_folder)
        
        l2.addWidget(icon2)
        l2.addLayout(v2, 1)
        l2.addWidget(btn2)
        layout.addWidget(self.card_res)

        # =================================================
        # 3. Export Directory (UI Completely Redesigned)
        # =================================================
        self.card_export = CardWidget(self)
        # 使用 QHBoxLayout 保持和其他卡片一致的左右结构
        l_export = QHBoxLayout(self.card_export)
        l_export.setContentsMargins(20, 20, 20, 20)
        
        icon_exp = IconWidget(FluentIcon.SAVE, self)
        
        # 中间部分：标题 + 路径文本 (CaptionLabel)
        # 这实现了"文本框展示的方式换成和上面两个一样"
        v_exp_text = QVBoxLayout()
        lbl_exp_title = SubtitleLabel("Export Directory", self)
        self.lbl_exp_path = CaptionLabel(self.default_export_path, self)
        # 设置自动换行，防止路径太长撑破布局
        self.lbl_exp_path.setWordWrap(False) 
        v_exp_text.addWidget(lbl_exp_title)
        v_exp_text.addWidget(self.lbl_exp_path)
        
        # 右侧部分：文字 + 开关 + 按钮
        # 使用弹簧把它们推到最右边
        
        # 这个 Label 显示 "Default (Downloads)" 或 "Custom"
        # 放在开关左边，实现“开关在文字右边”
        self.lbl_switch_status = BodyLabel("Default (Downloads)", self)
        self.lbl_switch_status.setStyleSheet("color: #666;") # 稍微灰色一点，区分度更好

        self.switch_custom_path = SwitchButton(self)
        # 我们手动控制文字标签，所以这里就不设置 OnText/OffText 了，或者设为空
        self.switch_custom_path.setOnText("")
        self.switch_custom_path.setOffText("")
        self.switch_custom_path.checkedChanged.connect(self.toggle_path_mode)
        
        self.btn_browse_path = PushButton("Browse", self)
        self.btn_browse_path.clicked.connect(self.browse_path)
        self.btn_browse_path.setEnabled(False) # 默认禁用
        
        # 组装 Export 卡片布局
        l_export.addWidget(icon_exp)
        l_export.addLayout(v_exp_text, 1) # 给路径文字分配更多空间
        
        l_export.addStretch(0) # 这是一个小的弹簧，或者是固定间距
        l_export.addWidget(self.lbl_switch_status) # 文字
        l_export.addSpacing(10)
        l_export.addWidget(self.switch_custom_path) # 开关 (在文字右边)
        l_export.addSpacing(20)
        l_export.addWidget(self.btn_browse_path) # 按钮
        
        layout.addWidget(self.card_export)

        # =================================================
        # 4. Optimization Mode
        # =================================================
        self.card_mode = CardWidget(self)
        l_mode = QHBoxLayout(self.card_mode)
        l_mode.setContentsMargins(20, 20, 20, 20)
        
        icon_mode = IconWidget(FluentIcon.SPEED_HIGH, self)
        lbl_mode = SubtitleLabel("Optimization Mode", self)
        
        self.cb_smt = CheckBox("SMT (Fast)", self)
        self.cb_opt = CheckBox("OPT (Ultra)", self)
        
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

        # =================================================
        # 5. Optimization Weights (Animation Supported)
        # =================================================
        self.card_weights = CardWidget(self)
        l_weights = QVBoxLayout(self.card_weights)
        l_weights.setContentsMargins(20, 20, 20, 20)
        l_weights.setSpacing(10)
        
        # Header
        w_header = QHBoxLayout()
        w_header.setContentsMargins(0,0,0,0)
        w_title = SubtitleLabel("Optimization Weights (Sum = 1.0)", self)
        w_header.addWidget(w_title)
        w_header.addStretch(1)
        l_weights.addLayout(w_header)
        
        # Weights Rows
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
        
        # Initialize dictionary for auto-balancing
        self.prev_vals = {
            self.spin_energy: 0.4,
            self.spin_use: 0.3,
            self.spin_co2: 0.3
        }
        
        # Connect signals
        self.spin_energy.valueChanged.connect(lambda v: self.balance_weights(self.spin_energy, v))
        self.spin_use.valueChanged.connect(lambda v: self.balance_weights(self.spin_use, v))
        self.spin_co2.valueChanged.connect(lambda v: self.balance_weights(self.spin_co2, v))
        
        # Default hidden with height 0
        self.card_weights.setMaximumHeight(0)
        self.card_weights.setVisible(False)

        # =================================================
        # Run Button & Progress
        # =================================================
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
    # Animation Logic
    # -----------------------------------------------------
    def toggle_weights_animation(self, show):
        if show and self.card_weights.isVisible() and self.card_weights.maximumHeight() > 0:
            return
        if not show and not self.card_weights.isVisible():
            return

        self.card_weights.setMaximumHeight(16777215) 
        self.card_weights.adjustSize()
        target_height = self.card_weights.sizeHint().height()

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

    # -----------------------------------------------------
    # Logic: Mode Selection
    # -----------------------------------------------------
    def on_smt_checked(self, state):
        if state == Qt.CheckState.Checked.value: 
            self.cb_opt.blockSignals(True)
            self.cb_opt.setChecked(False)
            self.cb_opt.blockSignals(False)
            
            self.mode_index = 0 # Fast
            self.toggle_weights_animation(False)
            self.btn_run.setText("Start Calculation in SMT Mode")
            self.update_run_button_style(0)
            self.notify_color_change("#107C10")
        else:
            if not self.cb_opt.isChecked():
                self.cb_smt.blockSignals(True)
                self.cb_smt.setChecked(True)
                self.cb_smt.blockSignals(False)

    def on_opt_checked(self, state):
        if state == Qt.CheckState.Checked.value: 
            self.cb_smt.blockSignals(True)
            self.cb_smt.setChecked(False)
            self.cb_smt.blockSignals(False)
            
            self.mode_index = 2 # Ultra
            self.toggle_weights_animation(True)
            self.btn_run.setText("Start Calculation in OPT Mode")
            self.update_run_button_style(2)
            self.notify_color_change("#FF8C00")
        else:
            if not self.cb_smt.isChecked():
                self.cb_opt.blockSignals(True)
                self.cb_opt.setChecked(True)
                self.cb_opt.blockSignals(False)

    def update_run_button_style(self, mode_idx):
        if mode_idx == 0: color_hex = "#107C10" 
        else: color_hex = "#FF8C00" 
        
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

    def notify_color_change(self, color_hex):
        main_win = self.window()
        if isinstance(main_win, FluentWindow) and hasattr(main_win, 'results_page'):
            main_win.results_page.set_export_button_color(color_hex)

    # -----------------------------------------------------
    # Logic: Weights Balancing
    # -----------------------------------------------------
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

    def get_weights(self):
        return (self.spin_energy.value(), self.spin_use.value(), self.spin_co2.value())

    # -----------------------------------------------------
    # Logic: Export Path
    # -----------------------------------------------------
    def toggle_path_mode(self, checked):
        self.btn_browse_path.setEnabled(checked)
        if checked:
            # Custom Mode
            self.lbl_switch_status.setText("Custom Path")
            # 保持之前选择的路径，或者如果是默认路径，则允许用户修改
            if self.current_export_path == self.default_export_path:
                 # 如果当前是默认路径，切换时可以保持，也可以置空，这里选择保持显示
                 pass
        else:
            # Default Mode
            self.lbl_switch_status.setText("Default (Downloads)")
            # 恢复默认路径显示
            self.current_export_path = self.default_export_path
            self.lbl_exp_path.setText(self.current_export_path)

    def browse_path(self):
        # 使用 os.path.normpath 处理初始路径
        start_dir = self.current_export_path if os.path.exists(self.current_export_path) else os.getcwd()
        d = QFileDialog.getExistingDirectory(self, "Select Export Directory", start_dir)
        if d:
            # [关键] 规范化路径显示 (处理 / 和 \)
            norm_d = os.path.normpath(d)
            self.current_export_path = norm_d
            self.lbl_exp_path.setText(norm_d)

    def get_export_path(self):
        return self.lbl_exp_path.text()

    # -----------------------------------------------------
    # Logic: File Selection & Running
    # -----------------------------------------------------
    def select_recipe(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Recipe XML", os.getcwd(), "XML Files (*.xml)")
        if f:
            self.recipe_path = os.path.normpath(f)
            self.lbl_recipe_val.setText(os.path.basename(self.recipe_path))
            self.check_ready()

    def select_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Resources Folder", os.getcwd())
        if d:
            self.resource_dir = os.path.normpath(d)
            self.lbl_res_val.setText(self.resource_dir)
            self.check_ready()

    def check_ready(self):
        if self.recipe_path and self.resource_dir:
            self.btn_run.setEnabled(True)

    def run_process(self):
        self.btn_run.setEnabled(False)
        self.log_callback("Starting Process...")
        
        weights = self.get_weights()
        
        self.worker = SMTWorker(self.recipe_path, self.resource_dir, self.mode_index, weights)
        self.worker.log_signal.connect(self.log_callback)
        self.worker.progress_signal.connect(lambda c, t: (self.pbar.setMaximum(t), self.pbar.setValue(c)))
        self.worker.error_signal.connect(lambda e: InfoBar.error(title="Error", content=e, parent=self.window()))
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, results, context_data):
        self.btn_run.setEnabled(True)
        main = self.window()
        if isinstance(main, FluentWindow):
            if hasattr(main, 'results_page') and hasattr(main, 'switchTo'):
                main.results_page.set_data(results, context_data)
                main.switchTo(main.results_page)
                InfoBar.success(title="Completed", content=f"Calculation finished.", parent=main, position=InfoBarPosition.TOP_RIGHT)