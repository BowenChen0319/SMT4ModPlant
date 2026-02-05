# Code/GUI/Results.py
import os
from typing import List, Dict
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView, QHBoxLayout
from qfluentwidgets import TableWidget, SubtitleLabel, PrimaryPushButton, InfoBar, InfoBarPosition, CheckBox

# Import Generator
from Code.Transformator.MasterRecipeGenerator import generate_b2mml_master_recipe

class ResultsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("results_widget")
        
        # Store context data for export
        self.context_data = None
        self.current_color_hex = "#107C10" # Default Green
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0) 
        
        # Header with Title and Export Button
        header_layout = QHBoxLayout()
        self.title = SubtitleLabel("Calculation Results", self)
        
        self.btn_export = PrimaryPushButton("Export Selected", self)
        self.btn_export.setEnabled(False) # Disabled until checkbox checked
        self.btn_export.clicked.connect(self.export_solution)
        
        header_layout.addWidget(self.title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_export)
        
        self.table = TableWidget(self)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setWordWrap(True)
        
        self.table.setSelectionMode(TableWidget.SelectionMode.NoSelection)
        self.table.itemChanged.connect(self.on_item_changed)
        
        layout.addLayout(header_layout)
        layout.addWidget(self.table, 1)

    def set_export_button_color(self, color_hex):
        self.current_color_hex = color_hex
        self.update_button_style()

    def update_button_style(self):
        style = f"""
            PrimaryPushButton {{
                background-color: {self.current_color_hex};
                border: 1px solid {self.current_color_hex};
                border-radius: 6px;
                color: white;
            }}
            PrimaryPushButton:hover {{
                background-color: {self.current_color_hex};
                opacity: 0.9;
            }}
            PrimaryPushButton:pressed {{
                background-color: {self.current_color_hex};
                opacity: 0.8;
            }}
            PrimaryPushButton:disabled {{
                background-color: #cccccc;
                border: 1px solid #cccccc;
                color: #666666;
            }}
        """
        self.btn_export.setStyleSheet(style)

    def set_data(self, gui_data: List[Dict], context_data: Dict):
        self.context_data = context_data
        self.update_table(gui_data)
        self.btn_export.setEnabled(False)

    def on_item_changed(self, item):
        """Enable export button if at least one checkbox is checked"""
        if item.column() == 0: # Only check changes in the Checkbox column
            checked_count = 0
            for r in range(self.table.rowCount()):
                chk_item = self.table.item(r, 0)
                if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                    checked_count += 1
            
            self.btn_export.setEnabled(checked_count > 0)
            if checked_count > 0:
                self.btn_export.setText(f"Export ({checked_count})")
            else:
                self.btn_export.setText("Export Selected")

    def export_solution(self):
        selected_sol_ids = set()
        for r in range(self.table.rowCount()):
            chk_item = self.table.item(r, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                sol_id_item = self.table.item(r, 1)
                if sol_id_item and sol_id_item.text().isdigit():
                    selected_sol_ids.add(int(sol_id_item.text()))
        
        if not selected_sol_ids: return

        # 2. Get Output Path
        save_dir = ""
        p = self.parent()
        while p is not None:
            if hasattr(p, 'get_export_path'):
                save_dir = p.get_export_path()
                break
            p = p.parent()
        
        if not save_dir or not os.path.exists(save_dir):
            # Normalize to platform separators (handles Windows vs. Unix)
            save_dir = os.path.normpath(os.path.expanduser("~/Downloads"))

        # 3. Generate Files
        success_count = 0
        try:
            for sol_id in selected_sol_ids:
                filename = f"MasterRecipe_Sol_{sol_id}.xml"
                full_path = os.path.join(save_dir, filename)
                
                generate_b2mml_master_recipe(
                    resources_data=self.context_data['resources'],
                    solutions_data_list=self.context_data['solutions'],
                    general_recipe_data=self.context_data['recipe'],
                    selected_solution_id=sol_id,
                    output_path=full_path
                )
                success_count += 1
            
            InfoBar.success(
                title="Export Successful",
                content=f"Successfully exported {success_count} recipe(s) to {save_dir}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self.window()
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error(
                title="Export Failed",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window()
            )

    def update_table(self, data: List[Dict]):
        # Determine if 'composite_score' exists in data
        has_score = False
        if data and len(data) > 0:
            for row in data:
                if row and 'composite_score' in row: 
                    has_score = True
                    break
        
        # Set up headers based on presence of score
        if has_score:
            headers = ["Export", "Sol ID", "Score", "Step", "Description", "Resource", "Capabilities", "Energy", "Use", "CO2"]
            col_count = 10
        else:
            headers = ["Export", "Sol ID", "Step", "Description", "Resource", "Capabilities", "Status"]
            col_count = 7
            
        self.table.setColumnCount(col_count)
        self.table.setHorizontalHeaderLabels(headers)
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        cap_col_idx = 6 if has_score else 5
        self.table.horizontalHeader().setSectionResizeMode(cap_col_idx, QHeaderView.ResizeMode.Stretch)

        self.table.setRowCount(len(data))
        self.table.blockSignals(True) # Prevent signals during setup

        last_sol_id = -1

        for r, row_data in enumerate(data):
 
            if not row_data:
                for c in range(col_count):
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.table.setItem(r, c, item)
                continue

            current_sol_id = row_data.get('solution_id', -1)

            # Col 0: Checkbox
            chk_item = QTableWidgetItem()

            if current_sol_id != last_sol_id and current_sol_id != -1:
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                last_sol_id = current_sol_id
            else:

                chk_item.setFlags(Qt.ItemFlag.NoItemFlags)
            
            self.table.setItem(r, 0, chk_item)


            if has_score:
                self.table.setItem(r, 1, QTableWidgetItem(str(row_data.get('solution_id', ''))))
                self.table.setItem(r, 2, QTableWidgetItem(f"{row_data.get('composite_score', 0):.2f}"))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['step_id'])))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data['description'])))
                self.table.setItem(r, 5, QTableWidgetItem(str(row_data['resource'])))
                self.table.setItem(r, 6, QTableWidgetItem(str(row_data['capabilities'])))
                self.table.setItem(r, 7, QTableWidgetItem(f"{row_data.get('energy_cost', 0):.1f}"))
                self.table.setItem(r, 8, QTableWidgetItem(f"{row_data.get('use_cost', 0):.1f}"))
                self.table.setItem(r, 9, QTableWidgetItem(f"{row_data.get('co2_footprint', 0):.1f}"))
            else:
                self.table.setItem(r, 1, QTableWidgetItem(str(row_data.get('solution_id', ''))))
                self.table.setItem(r, 2, QTableWidgetItem(str(row_data['step_id'])))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['description'])))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data['resource'])))
                self.table.setItem(r, 5, QTableWidgetItem(str(row_data['capabilities'])))
                status_item = QTableWidgetItem(str(row_data['status']))
                status_item.setForeground(QColor("#28a745"))
                self.table.setItem(r, 6, status_item)
        
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
