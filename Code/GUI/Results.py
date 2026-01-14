# Code/GUI/Results.py
from typing import List, Dict
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView
from qfluentwidgets import TableWidget, SubtitleLabel

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