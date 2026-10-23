"""A desktop window: edit the parameters, run the study, look at the plots.

The study runs as a separate `stackfem study` process, so the window stays
responsive and shows its output as it comes. Start with `stackfem-gui [file]`.
"""

import copy
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QFontDatabase, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import params

DEFAULT = Path(__file__).resolve().parents[2] / "params" / "module.toml"

LAYER_COLUMNS = [("name", "name"), ("material", "material"), ("width", "width [mm]"),
                 ("depth", "depth [mm]"), ("thickness", "thickness [mm]"), ("mesh_size", "mesh size [mm]")]
MATERIAL_COLUMNS = [("name", "name"), ("conductivity", "k [W/(m K)]"), ("youngs_modulus", "E [GPa]"),
                    ("poisson", "Poisson"), ("expansion", "CTE [ppm/K]")]
# (section, key, label) of every single-value field; a blank optional field is left out.
FIELDS = {
    "Heat load and cooling": [
        ("load", "source", "Heat source layer"),
        ("load", "power", "Power [W]"),
        ("load", "sink", "Coolant temperature [°C]"),
        ("load", "film", "Film coefficient [W/(m² K)]"),
    ],
    "Mesh and study": [
        ("mesh", "grading", "Size grading distance [mm]"),
        ("mesh", "refinement_ratio", "Refinement ratio per level"),
        ("study", "levels", "Levels (1 = baseline only)"),
        ("quality", "min_sicn", "Worst SICN allowed"),
        ("quality", "poor_sicn", "Poor element below SICN"),
        ("quality", "max_poor_fraction", "Poor elements allowed (fraction)"),
    ],
    "Thermal stress": [
        ("mechanics", "stress_free", "Stress-free temperature [°C]"),
    ],
}
CHOICES = [("mechanics", "support", "Support", ["flat", "free"]),
           ("mechanics", "solver", "Solver", ["direct", "iterative"])]
PLOTS = [("Convergence", "convergence.png"), ("Profile", "profile.png"),
         ("Die top", "top.png"), ("Stress", "stress.png")]


def parse(text):
    """A field's text as an int, a float, or else the text itself."""
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text


def show(value):
    return "" if value is None else str(value)


class Picture(QLabel):
    """An image that scales to fit its space."""

    def __init__(self):
        super().__init__("Run the study to see this plot.")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(200, 150)
        self.pixmap_ = None

    def load(self, path):
        self.pixmap_ = QPixmap(str(path)) if path.exists() else None
        if not self.pixmap_:
            self.setText("Run the study to see this plot.")
        self.fit()

    def fit(self):
        if self.pixmap_:
            self.setPixmap(self.pixmap_.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        self.fit()
        super().resizeEvent(event)


class Window(QMainWindow):
    def __init__(self, path=DEFAULT):
        super().__init__()
        self.resize(1400, 900)
        self.process = None
        self.base, self.path = {}, Path(path)

        self.layers = self.table(LAYER_COLUMNS)
        self.materials = self.table(MATERIAL_COLUMNS)
        self.name = QLineEdit()
        self.name.editingFinished.connect(self.show_plots)  # another name means other results
        self.fields, self.choices = {}, {}

        form = QVBoxLayout()
        top = QFormLayout()
        top.addRow("Name (results go to results/<name>)", self.name)
        form.addLayout(top)
        form.addWidget(self.table_box("Layers, bottom to top", self.layers))
        form.addWidget(self.table_box("Materials", self.materials))
        for title, fields in FIELDS.items():
            box = QGroupBox(title)
            rows = QFormLayout(box)
            rows.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for section, key, label in fields:
                self.fields[section, key] = QLineEdit()
                rows.addRow(label, self.fields[section, key])
            self.fields.get(("load", "film"), QLineEdit()).setPlaceholderText(
                "blank: bottom held at the coolant temperature")
            if title == "Thermal stress":
                box.setCheckable(True)
                self.mechanics = box
                for section, key, label, options in CHOICES:
                    self.choices[section, key] = QComboBox()
                    self.choices[section, key].addItems(options)
                    rows.addRow(label, self.choices[section, key])
            form.addWidget(box)
        form.addStretch()

        buttons = QHBoxLayout()
        for text, slot in [("Open…", self.open), ("Save as…", self.save_as)]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        self.run_button = QPushButton("Run")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run)
        buttons.addWidget(self.run_button)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setLayout(form)
        scroll.setWidget(inner)
        left_layout.addWidget(scroll)
        left_layout.addLayout(buttons)

        self.tabs = QTabWidget()
        self.pictures = {}
        for title, file in PLOTS:
            self.pictures[file] = Picture()
            self.tabs.addTab(self.pictures[file], title)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setPlaceholderText("Output from the study appears here.")
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))  # keeps its tables lined up
        right = QSplitter(Qt.Vertical)
        right.addWidget(self.tabs)
        right.addWidget(self.log)
        right.setSizes([650, 250])

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([560, 840])
        self.setCentralWidget(split)
        self.load(path)

    # ---- the form ----

    def table(self, columns):
        t = QTableWidget(0, len(columns))
        t.setHorizontalHeaderLabels([header for _, header in columns])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        t.setMinimumHeight(170)
        return t

    def table_box(self, title, table):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.addWidget(table)
        row = QHBoxLayout()
        for text, slot in [("Add row", lambda: table.insertRow(table.rowCount())),
                           ("Remove row", lambda: table.removeRow(table.currentRow()))]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        return box

    @staticmethod
    def fill(table, columns, rows):
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (key, _) in enumerate(columns):
                table.setItem(r, c, QTableWidgetItem(show(row.get(key))))

    @staticmethod
    def rows(table, columns):
        out = []
        for r in range(table.rowCount()):
            cells = {key: table.item(r, c).text().strip() if table.item(r, c) else ""
                     for c, (key, _) in enumerate(columns)}
            if any(cells.values()):
                out.append({k: parse(v) for k, v in cells.items() if v})
        return out

    def load(self, path):
        try:
            p = params.load(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Could not open the file", f"{path}\n\n{e}")
            return
        self.base, self.path = p, Path(path)
        self.setWindowTitle(f"StackFEM — {self.path.name}")
        self.name.setText(p["name"])
        self.fill(self.layers, LAYER_COLUMNS,
                  [dict(l, width=l["size"][0], depth=l["size"][1]) for l in p["layer"]])
        self.fill(self.materials, MATERIAL_COLUMNS,
                  [dict(m, name=name) for name, m in p["material"].items()])
        for (section, key), field in self.fields.items():
            field.setText(show(p.get(section, {}).get(key)))
        self.mechanics.setChecked("mechanics" in p)
        for (section, key), combo in self.choices.items():
            combo.setCurrentText(p.get(section, {}).get(key, combo.itemText(0)))
        self.show_plots()

    def read_form(self):
        """The parameters as the form now shows them. Raises ValueError if they don't check out."""
        p = copy.deepcopy(self.base)  # keeps anything in the file the form doesn't show
        p["name"] = self.name.text().strip()
        p["layer"] = []
        for row in self.rows(self.layers, LAYER_COLUMNS):
            try:
                row["size"] = [float(row.pop("width")), float(row.pop("depth"))]
            except KeyError as e:
                raise ValueError(f"layer '{row.get('name', '?')}' needs a width and depth") from e
            p["layer"].append(row)
        p["material"] = {str(row.pop("name")): row for row in self.rows(self.materials, MATERIAL_COLUMNS)}

        if self.mechanics.isChecked():
            p.setdefault("mechanics", {})
        else:
            p.pop("mechanics", None)
        for (section, key), field in self.fields.items():
            if section not in p:
                continue
            if field.text().strip():
                p[section][key] = parse(field.text().strip())
            else:
                p[section].pop(key, None)
        for (section, key), combo in self.choices.items():
            if section in p:
                p[section][key] = combo.currentText()
        try:
            return params.check(p)
        except KeyError as e:
            raise ValueError(f"missing value: {e}") from e
        except TypeError as e:
            raise ValueError(f"a number was expected: {e}") from e

    def checked_form(self):
        try:
            return self.read_form()
        except ValueError as e:
            QMessageBox.warning(self, "Check the parameters", str(e))
            return None

    # ---- buttons ----

    def open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open parameters", str(self.path.parent), "TOML (*.toml)")
        if path:
            self.load(path)

    def save_as(self):
        p = self.checked_form()
        if p is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save parameters", str(self.path), "TOML (*.toml)")
        if path:
            Path(path).write_text(params.dumps(p), encoding="utf-8")
            self.base, self.path = p, Path(path)
            self.setWindowTitle(f"StackFEM — {self.path.name}")

    def out(self):
        return Path("results") / self.name.text().strip()

    def run(self):
        p = self.checked_form()
        if p is None:
            return
        out = self.out()
        out.mkdir(parents=True, exist_ok=True)
        # The study reads a file, so the form is written next to its results.
        form_file = out / "form.toml"
        form_file.write_text(params.dumps(p), encoding="utf-8")

        self.log.clear()
        self.show_plots()  # don't leave an earlier run's plots up while this one runs
        self.run_button.setEnabled(False)
        self.run_button.setText("Running…")
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.start(sys.executable, ["-u", "-m", "stackfem.cli", "study", str(form_file), "--out", str(out)])

    def read_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.ensureCursorVisible()

    def finished(self, code, _status):
        self.read_output()
        self.run_button.setEnabled(True)
        self.run_button.setText("Run")
        self.log.appendPlainText("\nFinished." if code == 0 else f"\nStopped with an error (exit code {code}).")
        self.show_plots()
        if code == 0:
            self.tabs.setCurrentIndex(0)

    def show_plots(self):
        for file, picture in self.pictures.items():
            picture.load(self.out() / file)

    def closeEvent(self, event):
        if self.process and self.process.state() != QProcess.NotRunning:
            answer = QMessageBox.question(self, "A study is running",
                                          "Close the window and stop the study?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.process.kill()  # ponytail: a ccx already started finishes on its own
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = Window(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
