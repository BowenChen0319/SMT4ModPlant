# Code/GUI/Settings.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    CardWidget, IconWidget, BodyLabel, SwitchButton, 
    TitleLabel, SubtitleLabel, DoubleSpinBox, 
    FluentIcon, setTheme, Theme
)

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