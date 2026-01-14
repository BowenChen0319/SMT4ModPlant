# Code/GUI/Results.py
import os
from typing import List, Dict
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView, QHBoxLayout
from qfluentwidgets import TableWidget, SubtitleLabel, PrimaryPushButton, InfoBar, InfoBarPosition

# Import Generator
from Code.Transformator.MasterRecipeGenerator import generate_b2mml_master_recipe

class ResultsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("results_page")
        
        # Store context data for export
        self.context_data = None
        self.current_color_hex = "#107C10" # Default Green
        
        layout = QVBoxLayout(self)
        
        # Header with Title and Export Button
        header_layout = QHBoxLayout()
        self.title = SubtitleLabel("Calculation Results", self)
        
        self.btn_export = PrimaryPushButton("Export Master Recipe", self)
        self.btn_export.setFixedWidth(200)
        self.btn_export.setEnabled(False) # Disabled until selection
        self.btn_export.clicked.connect(self.export_solution)
        
        header_layout.addWidget(self.title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_export)
        
        self.table = TableWidget(self)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setWordWrap(True)
        # Enable row selection
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(TableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        
        layout.addLayout(header_layout)
        layout.addWidget(self.table, 1)

    def set_export_button_color(self, color_hex):
        """Called by Home to sync color"""
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
        """Receive data from Home"""
        self.context_data = context_data
        self.update_table(gui_data)
        self.btn_export.setEnabled(False) # Reset button

    def on_selection_changed(self):
        # Enable button only if a valid row with Solution ID is selected
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.btn_export.setEnabled(False)
            return
        
        # Get the Solution ID from the first column of the selected row
        row = selected_items[0].row()
        item = self.table.item(row, 0) # Col 0 is Sol ID
        
        if item and item.text().isdigit():
            self.btn_export.setEnabled(True)
        else:
            self.btn_export.setEnabled(False)

    def export_solution(self):
        # 1. Get Selected ID
        selected_items = self.table.selectedItems()
        if not selected_items: return
        row = selected_items[0].row()
        sol_id_text = self.table.item(row, 0).text()
        
        if not sol_id_text.isdigit(): return
        sol_id = int(sol_id_text)
        
        # 2. Get Output Path from Settings
        # Access settings via window().settings_page
        main_win = self.window()
        save_dir = ""
        if hasattr(main_win, 'settings_page'):
            save_dir = main_win.settings_page.get_export_path()
        else:
            save_dir = os.path.expanduser("~/Downloads")
            
        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir)
            except:
                save_dir = os.path.expanduser("~/Downloads")

        filename = f"MasterRecipe_Sol_{sol_id}.xml"
        full_path = os.path.join(save_dir, filename)
        
        # 3. Call Generator
        try:
            generate_b2mml_master_recipe(
                resources_data=self.context_data['resources'],
                solutions_data_list=self.context_data['solutions'],
                general_recipe_data=self.context_data['recipe'],
                selected_solution_id=sol_id,
                output_path=full_path
            )
            
            InfoBar.success(
                title="Export Successful",
                content=f"Saved to: {full_path}",
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
        # [Same logic as before, just kept here for context]
        has_score = False
        if data and len(data) > 0:
            for row in data:
                if row: 
                    if 'composite_score' in row: 
                        has_score = True
                    break
        
        if has_score:
            filtered_data = []
            temp_block = []
            for row in data:
                if not row:
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