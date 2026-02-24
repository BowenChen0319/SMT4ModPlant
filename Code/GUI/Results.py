# Code/GUI/Results.py
import os
from typing import List, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidgetItem,
    QHeaderView,
    QHBoxLayout,
    QFileDialog,
    QSizePolicy,
)

from qfluentwidgets import (
    TableWidget,
    SubtitleLabel,
    PushButton,
    InfoBar,
    InfoBarPosition,
    CheckBox,
)

# Import Generator
from Code.Transformator.MasterRecipeGenerator import generate_b2mml_master_recipe

# Validation helpers
from Code.Transformator.MasterRecipeValidator import (
    validate_master_recipe_xml,
    validate_master_recipe_parameters,
)

# For on-demand parsing if no cached resources exist
try:
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
except Exception:
    parse_capabilities_robust = None


class ResultsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("results_widget")

        # Store context data for export + parameter validation
        self.context_data: Optional[Dict] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)

        # Header with Title and Buttons
        header_layout = QHBoxLayout()
        self.title = SubtitleLabel("Calculation Results", self)

        # --- NEW: validation buttons ---
        self.btn_validate = PushButton("Validate Master Recipe", self)
        self.btn_validate.setVisible(False)
        self.btn_validate.clicked.connect(self.validate_master_recipe)

        self.btn_param_validate = PushButton("Parameter Validierung", self)
        self.btn_param_validate.setVisible(False)
        self.btn_param_validate.clicked.connect(self.validate_parameters)

        self.btn_export = PushButton("Export Selected", self)
        self.btn_export.setEnabled(False)  # Disabled until checkbox checked
        self.btn_export.clicked.connect(self.export_solution)

        # Keep buttons compact, but make validation actions a bit wider for labels.
        self.btn_validate.setMinimumWidth(170)
        self.btn_validate.setMaximumWidth(210)
        self.btn_validate.setFixedHeight(30)
        self.btn_validate.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_param_validate.setMinimumWidth(170)
        self.btn_param_validate.setMaximumWidth(210)
        self.btn_param_validate.setFixedHeight(30)
        self.btn_param_validate.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_export.setMinimumWidth(120)
        self.btn_export.setMaximumWidth(150)
        self.btn_export.setFixedHeight(30)
        self.btn_export.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        header_layout.addWidget(self.title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_validate)
        header_layout.addWidget(self.btn_param_validate)
        header_layout.addWidget(self.btn_export)

        self.table = TableWidget(self)
        self.table.verticalHeader().setVisible(False)
        self.table.setBorderVisible(True)
        self.table.setWordWrap(True)

        self.table.setSelectionMode(TableWidget.SelectionMode.NoSelection)
        self.table.itemChanged.connect(self.on_item_changed)

        layout.addLayout(header_layout)
        layout.addWidget(self.table, 1)

    # -------------------------
    # Styling sync (export button)
    # -------------------------
    def set_export_button_color(self, color_hex: str):
        # Keep API compatibility with Home.notify_color_change().
        # Export button intentionally uses the same default PushButton look
        # as validation buttons, so no mode-specific recoloring is applied.
        _ = color_hex
        self.update_button_style()

    def update_button_style(self):
        # Keep default qfluentwidgets PushButton appearance (same as Home "Select File")
        # to preserve native rounded-rectangle button styling.
        pass

    # -------------------------
    # Data / table
    # -------------------------
    def set_data(self, gui_data: List[Dict], context_data: Dict):
        """Called by Home to show results and cache context for export/validation."""
        self.context_data = context_data
        self.update_table(gui_data)
        self.btn_export.setEnabled(False)
        self.btn_export.setText("Export Selected")
        self.btn_validate.setVisible(False)
        self.btn_param_validate.setVisible(False)

    def on_item_changed(self, item: QTableWidgetItem):
        """Keep export button state in sync when item-based checkbox changes."""
        if item.column() != 0:
            return
        self._update_export_button_state()

    def _row_is_checked(self, row: int) -> bool:
        cb = self.table.cellWidget(row, 0)
        if isinstance(cb, CheckBox):
            return cb.isChecked()
        chk_item = self.table.item(row, 0)
        return bool(chk_item and chk_item.checkState() == Qt.CheckState.Checked)

    def _update_export_button_state(self):
        checked_count = 0
        for r in range(self.table.rowCount()):
            if self._row_is_checked(r):
                checked_count += 1

        self.btn_export.setEnabled(checked_count > 0)
        if checked_count > 0:
            self.btn_export.setText(f"Export ({checked_count})")
        else:
            self.btn_export.setText("Export Selected")

    # -------------------------
    # Export
    # -------------------------
    def export_solution(self):
        if not isinstance(self.context_data, dict):
            return

        selected_sol_ids = set()
        for r in range(self.table.rowCount()):
            if self._row_is_checked(r):
                sol_id_item = self.table.item(r, 1)
                if sol_id_item and (sol_id_item.text() or "").isdigit():
                    selected_sol_ids.add(int(sol_id_item.text()))

        if not selected_sol_ids:
            return

        main_win = self.window()
        save_dir = ""
        if hasattr(main_win, "settings_page"):
            try:
                save_dir = main_win.settings_page.get_export_path()
            except Exception:
                save_dir = ""

        if not save_dir:
            save_dir = os.path.expanduser("~/Downloads")

        if not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir)
            except Exception:
                save_dir = os.path.expanduser("~/Downloads")

        success_count = 0
        try:
            for sol_id in selected_sol_ids:
                filename = f"MasterRecipe_Sol_{sol_id}.xml"
                full_path = os.path.join(save_dir, filename)
                generate_b2mml_master_recipe(
                    resources_data=self.context_data["resources"],
                    solutions_data_list=self.context_data["solutions"],
                    general_recipe_data=self.context_data["recipe"],
                    selected_solution_id=sol_id,
                    output_path=full_path,
                )
                success_count += 1

            InfoBar.success(
                title="Export Successful",
                content=f"Successfully exported {success_count} recipe(s) to {save_dir}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self.window(),
            )
            if success_count > 0:
                self.btn_validate.setVisible(True)
                self.btn_param_validate.setVisible(True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error(
                title="Export Failed",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )

    # -------------------------
    # Logging helper
    # -------------------------
    def _append_log(self, msg: str):
        main = self.window()
        if hasattr(main, "log_page") and hasattr(main.log_page, "append_log"):
            try:
                main.log_page.append_log(msg)
                return
            except Exception:
                pass

    # =========================
    # Master Recipe Validation (XSD)
    # =========================
    def validate_master_recipe(self):
        main = self.window()
        start_dir = os.path.expanduser("~/Downloads")
        options = QFileDialog.Option.DontUseNativeDialog
        if hasattr(main, "settings_page"):
            try:
                d = main.settings_page.get_export_path()
                if d and os.path.isdir(d):
                    start_dir = d
            except Exception:
                pass

        xml_path, _ = QFileDialog.getOpenFileName(
            self,
            "Validate Master Recipe - Step 1/2: Select the Master Recipe XML file to validate",
            start_dir,
            "XML Files (*.xml);;All Files (*)",
            options=options,
        )
        if not xml_path:
            return

        schema_dir = QFileDialog.getExistingDirectory(
            self,
            "Validate Master Recipe - Step 2/2: Select the folder that contains XSD schema files",
            start_dir,
            options=options,
        )
        if not schema_dir:
            return
        if not any(name.lower().endswith(".xsd") for name in os.listdir(schema_dir)):
            InfoBar.error(
                title="Validation Error",
                content="Selected folder does not contain any .xsd files.",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                parent=self.window(),
            )
            return

        try:
            ok, errors, used_root = validate_master_recipe_xml(xml_path, schema_dir, root_xsd_path=None)

            self._append_log(f"[VALIDATION] XML: {xml_path}")
            self._append_log(f"[VALIDATION] allschema: {schema_dir}")
            self._append_log(f"[VALIDATION] root XSD used: {used_root}")

            if ok:
                InfoBar.success(
                    title="Validation Passed",
                    content=f"XML conforms to XSD (root: {os.path.basename(used_root or '')})",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window(),
                )
                self._append_log("[VALIDATION] Result: PASSED")
                return

            preview = " | ".join(errors[:2])
            more = "" if len(errors) <= 2 else f" (+{len(errors) - 2} more)"
            InfoBar.error(
                title="Validation Failed",
                content=f"{preview}{more}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=8000,
                parent=self.window(),
            )
            self._append_log(f"[VALIDATION] Result: FAILED (errors={len(errors)})")
            for i, err in enumerate(errors[:50], start=1):
                self._append_log(f"  {i}. {err}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error(
                title="Validation Error",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )

    # =========================
    # Parameter Validation (XML parameters vs AAS capabilities)
    # =========================
    def validate_parameters(self):
        main = self.window()
        start_dir = os.path.expanduser("~/Downloads")
        options = QFileDialog.Option.DontUseNativeDialog
        if hasattr(main, "settings_page"):
            try:
                d = main.settings_page.get_export_path()
                if d and os.path.isdir(d):
                    start_dir = d
            except Exception:
                pass

        xml_path, _ = QFileDialog.getOpenFileName(
            self,
            "Parameter Validation - Step 1: Select the Master Recipe XML file (resource folder may be requested)",
            start_dir,
            "XML Files (*.xml);;All Files (*)",
            options=options,
        )
        if not xml_path:
            return

        def _has_usable_resources(data) -> bool:
            if not isinstance(data, dict) or not data:
                return False
            # Accept both capability-map and uuid-index like shapes
            for v in data.values():
                if isinstance(v, list) and len(v) > 0:
                    return True
                if isinstance(v, dict) and len(v) > 0:
                    return True
            return False

        resources_data = None
        if isinstance(self.context_data, dict) and "resources" in self.context_data:
            resources_data = self.context_data.get("resources")

        # If cached resources are missing/invalid, parse on-demand
        if not _has_usable_resources(resources_data):
            if parse_capabilities_robust is None:
                InfoBar.error(
                    title="Parameter Validation Error",
                    content="AAS parser (parse_capabilities_robust) not available in this build.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self.window(),
                )
                return

            resource_dir = QFileDialog.getExistingDirectory(
                self,
                "Parameter Validation - Step 2: Select the resource folder (AAS XML/AASX)",
                start_dir,
                options=options,
            )
            if not resource_dir:
                return
            if not any(name.lower().endswith((".xml", ".aasx")) for name in os.listdir(resource_dir)):
                InfoBar.error(
                    title="Parameter Validation Error",
                    content="Selected folder does not contain any .xml or .aasx files.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window(),
                )
                return

            self._append_log(f"[PARAM-VALIDATION] Parsing resources from: {resource_dir}")
            resources_data = {}
            try:
                for fn in os.listdir(resource_dir):
                    if not (fn.lower().endswith(".xml") or fn.lower().endswith(".aasx")):
                        continue
                    full = os.path.join(resource_dir, fn)
                    res_name = os.path.splitext(fn)[0]
                    try:
                        caps = parse_capabilities_robust(full)
                        if caps:
                            resources_data[f"resource: {res_name}"] = caps
                    except Exception as pe:
                        self._append_log(f"[PARAM-VALIDATION] Warning: failed to parse {fn}: {pe}")
            except Exception as e:
                InfoBar.error(
                    title="Resource Parsing Failed",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    parent=self.window(),
                )
                return
            if not _has_usable_resources(resources_data):
                InfoBar.error(
                    title="Parameter Validation Error",
                    content="No valid resource capabilities could be parsed from selected folder.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=7000,
                    parent=self.window(),
                )
                return

        try:
            ok, errors, warnings, checked, details = validate_master_recipe_parameters(xml_path, resources_data)

            self._append_log(f"[PARAM-VALIDATION] XML: {xml_path}")
            self._append_log(f"[PARAM-VALIDATION] Checked parameters: {checked}")

            found_items = [d for d in details if d.get("status") == "FOUND"]
            missing_items = [d for d in details if d.get("status") == "MISSING"]
            self._append_log(f"[PARAM-VALIDATION] Matched: {len(found_items)} | Missing: {len(missing_items)}")

            for d in found_items[:50]:
                self._append_log(
                    f"  OK: {d.get('description')} -> id={d.get('raw_id') or d.get('uuid')} (uuid={d.get('uuid')}) "
                    f"in {d.get('resource_key')} / {d.get('capability_name')} / {d.get('property_name')} "
                    f"({d.get('property_unit')})"
                )

            for w in warnings[:100]:
                self._append_log(f"  WARN: {w}")
            for e in errors[:200]:
                self._append_log(f"  ERROR: {e}")

            if ok:
                InfoBar.success(
                    title="Parameter Validation Passed",
                    content=f"All {checked} parameters matched parsed AAS capabilities.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window(),
                )
            else:
                preview = " | ".join(errors[:2])
                more = "" if len(errors) <= 2 else f" (+{len(errors) - 2} more)"
                InfoBar.error(
                    title="Parameter Validation Failed",
                    content=f"{preview}{more}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=9000,
                    parent=self.window(),
                )

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._append_log("[PARAM-VALIDATION] Exception occurred:")
            self._append_log(traceback.format_exc())
            InfoBar.error(
                title="Parameter Validation Error",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )

    # -------------------------
    # Table rendering (kept compatible with existing columns)
    # -------------------------
    def _format_capabilities_text(self, raw_capabilities) -> str:
        """Format capabilities for readable full display in table cells."""
        if isinstance(raw_capabilities, (list, tuple, set)):
            return "\n".join(str(x) for x in raw_capabilities)
        text = str(raw_capabilities) if raw_capabilities is not None else ""
        if ", " in text:
            return text.replace(", ", ",\n")
        return text

    def update_table(self, data: List[Dict]):
        """Update results table. Adds a leading checkbox column."""
        if not data:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        # detect score mode
        has_score = any(isinstance(r, dict) and "composite_score" in r for r in data if r)

        # headers/columns (checkbox + previous layout)
        if has_score:
            headers = ["", "Sol ID", "Step", "Resource", "Capabilities", "Weighted Energy", "Weighted Use", "Weighted CO2"]
            self.table.setColumnCount(8)
        else:
            headers = ["", "Sol ID", "Step", "Description", "Resource", "Capabilities", "Status"]
            self.table.setColumnCount(7)

        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.clearSpans()
        self.table.setHorizontalHeaderLabels(headers)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 42)
        cap_col_idx = 4 if has_score else 5
        self.table.horizontalHeader().setSectionResizeMode(cap_col_idx, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionsClickable(False)
        self.table.horizontalHeader().setSortIndicatorShown(False)

        self.table.setRowCount(len(data))

        last_sol_id = -1
        for r, row_data in enumerate(data):
            if not row_data:
                for c in range(self.table.columnCount()):
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.table.setItem(r, c, item)
                continue

            current_sol_id = row_data.get("solution_id", -1)

            if has_score:
                if row_data.get("is_solution_header"):
                    # Checkbox and export ID are on the solution header row.
                    if current_sol_id != -1:
                        cb = CheckBox(self.table)
                        cb.stateChanged.connect(lambda _state: self._update_export_button_state())
                        self.table.setCellWidget(r, 0, cb)
                    else:
                        chk_item = QTableWidgetItem()
                        chk_item.setFlags(Qt.ItemFlag.NoItemFlags)
                        self.table.setItem(r, 0, chk_item)

                    self.table.setItem(r, 1, QTableWidgetItem(str(current_sol_id if current_sol_id != -1 else "")))
                    summary = f"Solution {current_sol_id}, Total Weighted Cost = {row_data.get('composite_score', 0):.2f}"
                    summary_item = QTableWidgetItem(summary)
                    summary_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.table.setItem(r, 2, summary_item)
                    self.table.setSpan(r, 2, 1, self.table.columnCount() - 2)
                else:
                    chk_item = QTableWidgetItem()
                    chk_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.table.setItem(r, 0, chk_item)
                    self.table.setItem(r, 1, QTableWidgetItem(""))
                    self.table.setItem(r, 2, QTableWidgetItem(str(row_data.get("step_id", ""))))
                    self.table.setItem(r, 3, QTableWidgetItem(str(row_data.get("resource", ""))))
                    self.table.setItem(r, 4, QTableWidgetItem(self._format_capabilities_text(row_data.get("capabilities", ""))))
                    self.table.setItem(r, 5, QTableWidgetItem(f"{row_data.get('energy_cost', 0):.1f}"))
                    self.table.setItem(r, 6, QTableWidgetItem(f"{row_data.get('use_cost', 0):.1f}"))
                    self.table.setItem(r, 7, QTableWidgetItem(f"{row_data.get('co2_footprint', 0):.1f}"))
            else:
                # checkbox: only show selectable checkbox for first row of each solution
                if current_sol_id != last_sol_id and current_sol_id != -1:
                    cb = CheckBox(self.table)
                    cb.stateChanged.connect(lambda _state: self._update_export_button_state())
                    self.table.setCellWidget(r, 0, cb)
                    last_sol_id = current_sol_id
                else:
                    chk_item = QTableWidgetItem()
                    chk_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.table.setItem(r, 0, chk_item)

                self.table.setItem(r, 1, QTableWidgetItem(str(row_data.get("solution_id", ""))))
                self.table.setItem(r, 2, QTableWidgetItem(str(row_data.get("step_id", ""))))
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data.get("description", ""))))
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data.get("resource", ""))))
                self.table.setItem(r, 5, QTableWidgetItem(self._format_capabilities_text(row_data.get("capabilities", ""))))
                status_item = QTableWidgetItem(str(row_data.get("status", "")))
                status_item.setForeground(QColor("#28a745"))
                self.table.setItem(r, 6, status_item)

        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(False)
        self._update_export_button_state()
