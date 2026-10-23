import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import MODULE  # noqa: E402
from stackfem import gui, params  # noqa: E402
from test_solver import needs_ccx  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = gui.Window(MODULE)
    yield w
    w.close()


def test_form_shows_the_file_unchanged(window):
    assert window.read_form() == params.load(MODULE)


def test_edits_reach_the_parameters(window):
    window.fields["load", "power"].setText("35")
    window.fields["load", "film"].setText("")
    window.layers.item(1, 4).setText("0.12")
    window.mechanics.setChecked(False)
    p = window.read_form()
    assert p["load"]["power"] == 35
    assert "film" not in p["load"]
    assert p["layer"][1]["thickness"] == 0.12
    assert "mechanics" not in p


def test_bad_values_are_caught_before_running(window):
    window.layers.item(0, 1).setText("unobtainium")
    with pytest.raises(ValueError, match="unobtainium"):
        window.read_form()
    window.layers.item(0, 1).setText("copper")
    window.fields["load", "power"].setText("lots")
    with pytest.raises(ValueError):
        window.read_form()


@needs_ccx
def test_run_reports_each_step_and_finishes(app, slab, tmp_path, monkeypatch):
    """A one-level run through the Run button, on a small slab, with the stress step."""
    from PySide6.QtCore import QEventLoop, QTimer

    monkeypatch.chdir(tmp_path)  # results/<name> lands in the temporary folder
    slab["study"]["levels"] = 1
    file = tmp_path / "slab.toml"
    file.write_text(params.dumps(slab), encoding="utf-8")
    w = gui.Window(file)
    w.run_button.click()
    assert w.run_button.text().startswith("Running… 0:0")
    assert "not frozen" in w.statusBar().currentMessage()
    assert "not frozen" in w.log.toPlainText()

    loop = QEventLoop()
    w.process.finished.connect(loop.quit)
    QTimer.singleShot(120_000, loop.quit)  # give up rather than hang the suite
    loop.exec()

    log = w.log.toPlainText()
    for line in ["meshing", "solving the heat flow", "solving the thermal stress", "Finished in"]:
        assert line in log
    assert w.run_button.text() == "Run" and w.run_button.isEnabled()
    assert w.statusBar().currentMessage() == ""
    assert (tmp_path / "results" / slab["name"] / "profile.png").exists()
    w.close()
