import os
import sys
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QSizePolicy,
    QFrame,
    QScrollArea,
)

from qfluentwidgets import (
    CardWidget,
    IconWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    PushButton,
    FluentIcon,
    InfoBarPosition,
)
from Code.GUI.Notifications import SafeInfoBar as InfoBar

from Code.Transformator.MasterRecipeValidator import (
    validate_master_recipe_xml_detailed,
    validate_master_recipe_parameters,
)

try:
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
except Exception:
    parse_capabilities_robust = None


class RecipeValidatorPage(QWidget):
    """Standalone page for recipe-level validation tools."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("recipe_validator_page")
        self.context_data: Optional[Dict] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(18)

        self.title = SubtitleLabel("Recipe Validator", self)
        layout.addWidget(self.title)

        # Card 1: XSD validation
        xsd_card = CardWidget(self)
        xsd_row = QHBoxLayout(xsd_card)
        xsd_row.setContentsMargins(20, 20, 20, 20)
        xsd_row.setSpacing(14)
        xsd_row.addWidget(IconWidget(FluentIcon.DOCUMENT, self))
        xsd_text = QVBoxLayout()
        xsd_title = SubtitleLabel("Validate Master Recipe", self)
        xsd_desc = BodyLabel("Check Master Recipe XML against selected XSD schema folder.", self)
        xsd_desc.setStyleSheet("color: #8A8A8A;")
        xsd_text.addWidget(xsd_title)
        xsd_text.addWidget(xsd_desc)
        xsd_row.addLayout(xsd_text, 1)
        self.btn_validate = PushButton("Run XSD Validation", self)
        self.btn_validate.setFixedHeight(34)
        self.btn_validate.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_validate.clicked.connect(self.validate_master_recipe)
        xsd_row.addWidget(self.btn_validate)
        layout.addWidget(xsd_card)

        # Card 2: Parameter validation
        param_card = CardWidget(self)
        param_row = QHBoxLayout(param_card)
        param_row.setContentsMargins(20, 20, 20, 20)
        param_row.setSpacing(14)
        param_row.addWidget(IconWidget(FluentIcon.ACCEPT, self))
        param_text = QVBoxLayout()
        param_title = SubtitleLabel("Parameter Validierung", self)
        param_desc = BodyLabel("Validate XML parameter IDs against parsed AAS capabilities.", self)
        param_desc.setStyleSheet("color: #8A8A8A;")
        param_text.addWidget(param_title)
        param_text.addWidget(param_desc)
        param_row.addLayout(param_text, 1)
        self.btn_param_validate = PushButton("Run Parameter Validation", self)
        self.btn_param_validate.setFixedHeight(34)
        self.btn_param_validate.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_param_validate.clicked.connect(self.validate_parameters)
        param_row.addWidget(self.btn_param_validate)
        layout.addWidget(param_card)

        # Result status area (replaces in-page validation log)
        status_card = CardWidget(self)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(20, 16, 20, 16)
        status_layout.setSpacing(10)
        self.status_dot = BodyLabel("●", self)
        self.status_dot.setStyleSheet("color: #8A8A8A; font-size: 18px;")
        self.status_text = SubtitleLabel("No Validation Run Yet", self)
        self.status_text.setWordWrap(True)
        status_layout.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        status_layout.addWidget(self.status_text, 1)
        layout.addWidget(status_card)

        self.details_card = CardWidget(self)
        self.details_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_layout = QVBoxLayout(self.details_card)
        details_layout.setContentsMargins(20, 18, 20, 18)
        details_layout.setSpacing(12)
        details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        details_header = QVBoxLayout()
        details_header.setContentsMargins(0, 0, 0, 0)
        details_header.setSpacing(2)
        details_header.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.details_title = SubtitleLabel("Validation Details", self)
        self.details_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.details_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.details_hint = CaptionLabel("All validation issues will appear here when a check fails.", self)
        self.details_hint.setStyleSheet("color: #8A8A8A;")
        self.details_hint.setWordWrap(True)
        self.details_hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.details_hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        details_header.addWidget(self.details_title)
        details_header.addWidget(self.details_hint)
        details_layout.addLayout(details_header)

        self.details_scroll = QScrollArea(self)
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.details_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.details_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.details_container = QWidget(self)
        self.details_container.setStyleSheet("background: transparent;")
        self.details_list_layout = QVBoxLayout(self.details_container)
        self.details_list_layout.setContentsMargins(0, 0, 0, 0)
        self.details_list_layout.setSpacing(10)
        self.details_scroll.setWidget(self.details_container)
        self.details_scroll.hide()
        details_layout.addWidget(self.details_scroll, 1)

        layout.addWidget(self.details_card, 1)
        self._show_validation_issues(
            title="Validation Details",
            hint="All validation issues will appear here when a check fails.",
            issues=[],
        )

    def set_context_data(self, context_data: Optional[Dict]):
        """Receive latest calculation context from Home page."""
        self.context_data = context_data if isinstance(context_data, dict) else None

    @staticmethod
    def _default_user_dir() -> str:
        downloads = os.path.normpath(os.path.join(os.path.expanduser("~"), "Downloads"))
        return downloads if os.path.isdir(downloads) else os.path.expanduser("~")

    @staticmethod
    def _program_dir() -> str:
        program_path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else os.getcwd()
        return os.path.dirname(program_path)

    @staticmethod
    def _dialog_options():
        options = QFileDialog.Option(0)
        if os.name != "nt":
            options |= QFileDialog.Option.DontUseNativeDialog
        return options

    def _open_file_dialog(self, title: str, start_dir: str, name_filter: str):
        dialog = QFileDialog(self)
        dialog.setWindowTitle(title)
        dialog.setDirectory(start_dir)
        dialog.setNameFilter(name_filter)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setOptions(self._dialog_options())
        if dialog.exec():
            files = dialog.selectedFiles()
            if files:
                return files[0]
        return ""

    def _open_directory_dialog(self, title: str, start_dir: str):
        dialog = QFileDialog(self)
        dialog.setWindowTitle(title)
        dialog.setDirectory(start_dir)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if os.name != "nt":
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        if dialog.exec():
            dirs = dialog.selectedFiles()
            if dirs:
                return dirs[0]
        return ""

    def _get_preferred_export_dir(self) -> str:
        """Resolve the export directory from the main window, with fallback."""
        main = self.window()
        if hasattr(main, "get_export_path"):
            try:
                export_dir = main.get_export_path()
                if export_dir:
                    return os.path.normpath(export_dir)
            except Exception:
                pass
        return self._default_user_dir()

    def _set_status(self, ok: bool, text: str):
        color = "#107C10" if ok else "#D13438"
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 18px;")
        self.status_text.setText(text)

    def _clear_validation_issue_widgets(self):
        while self.details_list_layout.count():
            item = self.details_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_issue_card(self, issue: Dict, index: int) -> QFrame:
        card = QFrame(self.details_container)
        card.setObjectName("validationIssueCard")
        card.setStyleSheet(
            """
            QFrame#validationIssueCard {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            """
        )

        outer = QHBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = QFrame(card)
        accent.setFixedWidth(5)
        accent.setStyleSheet("background-color: #D13438; border-top-left-radius: 14px; border-bottom-left-radius: 14px;")
        outer.addWidget(accent)

        content_wrap = QWidget(card)
        content_wrap.setStyleSheet("background: transparent;")
        content = QVBoxLayout(content_wrap)
        content.setContentsMargins(16, 14, 16, 14)
        content.setSpacing(6)

        badge = CaptionLabel(f"Issue {index:02d}", content_wrap)
        badge.setStyleSheet(
            "color: #FDE7E9; background-color: rgba(209, 52, 56, 0.22); "
            "border: 1px solid rgba(209, 52, 56, 0.45); border-radius: 10px; padding: 2px 8px;"
        )
        badge.setAlignment(Qt.AlignmentFlag.AlignLeft)
        content.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        title = BodyLabel(issue.get("title") or "Validation issue", content_wrap)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        content.addWidget(title)

        location_text = issue.get("location") or "Unknown location"
        location = CaptionLabel(location_text, content_wrap)
        location.setWordWrap(True)
        location.setStyleSheet("color: #8A8A8A;")
        content.addWidget(location)

        reason = BodyLabel(issue.get("reason") or issue.get("message") or "", content_wrap)
        reason.setWordWrap(True)
        reason.setStyleSheet("color: #F3F3F3;")
        content.addWidget(reason)

        extra = issue.get("extra") or ""
        if extra:
            extra_label = CaptionLabel(extra, content_wrap)
            extra_label.setWordWrap(True)
            extra_label.setStyleSheet("color: #B9B9B9;")
            content.addWidget(extra_label)

        outer.addWidget(content_wrap, 1)
        return card

    def _show_validation_issues(self, title: str, hint: str, issues: list[Dict]):
        self.details_title.setText(title)
        self.details_hint.setText(hint)
        self._clear_validation_issue_widgets()

        has_issues = len(issues) > 0
        self.details_scroll.setVisible(has_issues)

        if not has_issues:
            return

        for index, issue in enumerate(issues, start=1):
            self.details_list_layout.addWidget(self._build_issue_card(issue, index))
        self.details_list_layout.addStretch(1)

    @staticmethod
    def _normalize_issue_text(value) -> str:
        return str(value).strip() if value is not None else ""

    def _build_xsd_issue_items(self, details: list[Dict], errors: list[str]) -> list[Dict]:
        issues: list[Dict] = []

        for detail in details:
            message = self._normalize_issue_text(detail.get("message"))
            location = self._normalize_issue_text(detail.get("location")) or "Schema validation"
            path = self._normalize_issue_text(detail.get("path"))
            type_name = self._normalize_issue_text(detail.get("type_name"))

            extra_parts = []
            if path:
                extra_parts.append(f"XPath: {path}")
            if type_name:
                extra_parts.append(f"Type: {type_name}")

            issues.append({
                "title": location,
                "location": "Master Recipe XML",
                "reason": message or "Schema validation failed.",
                "extra": " | ".join(extra_parts),
            })

        if issues:
            return issues

        for err in errors:
            issues.append({
                "title": "Schema validation error",
                "location": "Master Recipe XML",
                "reason": self._normalize_issue_text(err),
            })
        return issues

    def _build_parameter_issue_items(self, details: list[Dict], errors: list[str]) -> list[Dict]:
        issues: list[Dict] = []
        for detail in details:
            status = detail.get("status")
            if status not in {"INVALID_PREFIX", "INVALID_ID", "UNKNOWN_UUID"}:
                continue

            desc = self._normalize_issue_text(detail.get("description")) or "Unnamed parameter"
            raw_id = self._normalize_issue_text(detail.get("raw_id"))
            uuid = self._normalize_issue_text(detail.get("uuid"))
            location = self._normalize_issue_text(detail.get("location")) or desc

            if status == "INVALID_PREFIX":
                reason = "The ID prefix is outside the allowed range."
            elif status == "INVALID_ID":
                reason = "The parameter ID could not be parsed as a valid UUID or OPC UA GUID."
            else:
                reason = "The UUID does not exist in the parsed AAS capability set."

            extra_parts = []
            if raw_id:
                extra_parts.append(f"ID: {raw_id}")
            if uuid:
                extra_parts.append(f"UUID: {uuid}")

            issues.append({
                "title": desc,
                "location": location,
                "reason": reason,
                "extra": " | ".join(extra_parts),
            })

        if issues:
            return issues

        for err in errors:
            issues.append({
                "title": "Parameter validation error",
                "location": "Master Recipe Parameter",
                "reason": self._normalize_issue_text(err),
            })
        return issues

    def validate_master_recipe(self):
        start_dir = self._get_preferred_export_dir()
        if not os.path.isdir(start_dir):
            start_dir = self._default_user_dir()

        xml_path = self._open_file_dialog(
            title="Validate Master Recipe - Step 1/2: Select Master Recipe XML",
            start_dir=start_dir,
            name_filter="XML Files (*.xml);;All Files (*)",
        )
        if not xml_path:
            return

        schema_dir = self._open_directory_dialog(
            title="Validate Master Recipe - Step 2/2: Select XSD Schema Folder",
            start_dir=self._program_dir(),
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
            ok, errors, used_root, error_details = validate_master_recipe_xml_detailed(
                xml_path,
                schema_dir,
                root_xsd_path=None,
            )

            if ok:
                self._set_status(True, f"Validate Master Recipe Passed (Root XSD: {os.path.basename(used_root or '')})")
                self._show_validation_issues(
                    title="Validation Details",
                    hint="No XML schema issues were detected in the selected Master Recipe.",
                    issues=[],
                )
                InfoBar.success(
                    title="Validation Passed",
                    content=f"XML conforms to XSD (root: {os.path.basename(used_root or '')})",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window(),
                )
                return

            preview = " | ".join(errors[:2])
            more = "" if len(errors) <= 2 else f" (+{len(errors) - 2} more)"
            self._set_status(False, f"Validate Master Recipe failed ({len(errors)} errors)")
            self._show_validation_issues(
                title=f"Schema Issues ({len(errors)})",
                hint="Each item shows where the XML schema check failed and why.",
                issues=self._build_xsd_issue_items(error_details, errors),
            )
            InfoBar.error(
                title="Validation Failed",
                content=f"{preview}{more}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=8000,
                parent=self.window(),
            )
        except Exception as e:
            self._set_status(False, f"Validate Master Recipe error: {e}")
            self._show_validation_issues(
                title="Validation Error",
                hint="The schema validation run ended with an exception.",
                issues=[{
                    "title": "Unexpected validation error",
                    "location": "Recipe Validator",
                    "reason": str(e),
                }],
            )
            InfoBar.error(
                title="Validation Error",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )

    def validate_parameters(self):
        start_dir = self._get_preferred_export_dir()
        if not os.path.isdir(start_dir):
            start_dir = self._default_user_dir()

        def _has_usable_resources(data) -> bool:
            if not isinstance(data, dict) or not data:
                return False
            for v in data.values():
                if isinstance(v, list) and len(v) > 0:
                    return True
                if isinstance(v, dict) and len(v) > 0:
                    return True
            return False

        resources_data = None
        if isinstance(self.context_data, dict) and "resources" in self.context_data:
            resources_data = self.context_data.get("resources")
        has_cached_resources = _has_usable_resources(resources_data)

        xml_dialog_title = (
            "Parameter Validation: Select Master Recipe XML"
            if has_cached_resources
            else "Parameter Validation - Step 1/2: Select Master Recipe XML"
        )
        xml_path = self._open_file_dialog(
            title=xml_dialog_title,
            start_dir=start_dir,
            name_filter="XML Files (*.xml);;All Files (*)",
        )
        if not xml_path:
            return

        if not has_cached_resources:
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

            resource_dir = self._open_directory_dialog(
                title="Parameter Validation - Step 2/2: Select Resource Folder (AAS XML/AASX/JSON)",
                start_dir=self._program_dir(),
            )
            if not resource_dir:
                return
            if not any(name.lower().endswith((".xml", ".aasx", ".json")) for name in os.listdir(resource_dir)):
                InfoBar.error(
                    title="Parameter Validation Error",
                    content="Selected folder does not contain any .xml, .aasx, or .json files.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self.window(),
                )
                return

            resources_data = {}
            try:
                for fn in os.listdir(resource_dir):
                    if not fn.lower().endswith((".xml", ".aasx", ".json")):
                        continue
                    full = os.path.join(resource_dir, fn)
                    res_name = os.path.splitext(fn)[0]
                    try:
                        caps = parse_capabilities_robust(full)
                        if caps:
                            resources_data[f"resource: {res_name}"] = caps
                    except Exception as pe:
                        pass
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

            if ok:
                self._set_status(True, f"Parameter Validierung passed: all {checked} parameters matched.")
                hint = "All parameters matched the parsed AAS capability data."
                if warnings:
                    hint = f"{hint} Warnings: {len(warnings)}."
                self._show_validation_issues(
                    title="Parameter Details",
                    hint=hint,
                    issues=[],
                )
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
                self._set_status(False, f"Parameter Validierung failed ({len(errors)} errors)")
                self._show_validation_issues(
                    title=f"Parameter Issues ({len(errors)})",
                    hint="Each item shows the failing parameter, its location, and the reason.",
                    issues=self._build_parameter_issue_items(details, errors),
                )
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
            self._set_status(False, f"Parameter Validierung error: {e}")
            self._show_validation_issues(
                title="Parameter Validation Error",
                hint="The parameter validation run ended with an exception.",
                issues=[{
                    "title": "Unexpected validation error",
                    "location": "Recipe Validator",
                    "reason": str(e),
                }],
            )
            InfoBar.error(
                title="Parameter Validation Error",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )
