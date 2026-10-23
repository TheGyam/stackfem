import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from conftest import MODULE  # noqa: E402
from stackfem import gui, params  # noqa: E402


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
