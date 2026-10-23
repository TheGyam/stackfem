import copy
import tomllib

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


@pytest.mark.parametrize("change, message", [
    (lambda p: p["mechanics"].update(support="glued"), "flat"),
    (lambda p: p["material"]["sic"].pop("expansion"), "expansion"),
    (lambda p: p["material"]["aln"].update(poisson=0.5), "poisson"),
    (lambda p: p["load"].update(film=0), "film"),
])
def test_bad_mechanics_and_cooling_are_rejected(module, change, message):
    p = copy.deepcopy(module)
    change(p)
    with pytest.raises(ValueError, match=message):
        params.check(p)


def test_mechanics_is_optional(module):
    p = copy.deepcopy(module)
    del p["mechanics"]
    for material in p["material"].values():
        del material["expansion"]
    params.check(p)


def test_written_file_reads_back_the_same(module):
    assert tomllib.loads(params.dumps(module)) == module
