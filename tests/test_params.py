import copy

import pytest

from stackfem import params


def test_module_file_loads(module):
    assert [l["name"] for l in module["layer"]] == ["baseplate", "solder", "substrate", "die_attach", "die"]
    assert params.layer_heights(module)[-1][1] == pytest.approx(3.03)


@pytest.mark.parametrize("change, message", [
    (lambda p: p["layer"][1].update(material="unobtainium"), "not defined"),
    (lambda p: p["layer"][1].update(thickness=0), "positive"),
    (lambda p: p["layer"][1].update(name="baseplate"), "unique"),
    (lambda p: p["load"].update(source="lid"), "not a layer"),
    (lambda p: p["mesh"].update(refinement_ratio=1.0), "above 1"),
])
def test_bad_files_are_rejected(module, change, message):
    p = copy.deepcopy(module)
    change(p)
    with pytest.raises(ValueError, match=message):
        params.check(p)
