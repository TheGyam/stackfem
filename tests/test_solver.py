import numpy as np
import pytest

from stackfem import mesh, params, post, solver


def have_ccx():
    try:
        solver.find_ccx()
        return True
    except FileNotFoundError:
        return False


needs_ccx = pytest.mark.skipif(not have_ccx(), reason="CalculiX (ccx) is not installed")


def test_heat_density_is_power_over_volume(slab):
    # 20 W in a 2 x 2 x 0.3 mm chip, in mW/mm^3
    assert solver.heat_density(slab) == pytest.approx(20_000 / 1.2)


def test_bottom_faces_cover_the_bottom_exactly_once(slab_mesh):
    p, data = slab_mesh
    conn = np.vstack(list(data["elements"].values()))
    area = 0.0
    for element, face in solver.bottom_faces(data):
        a, b, c = data["nodes"][conn[element - 1, list(solver.FACES[face - 1])] - 1]
        assert np.allclose([a[2], b[2], c[2]], 0)
        area += np.linalg.norm(np.cross(b - a, c - a)) / 2
    assert area == pytest.approx(4.0)


def test_reads_the_last_printed_increment(tmp_path):
    dat = tmp_path / "job.dat"
    dat.write_text(
        " temperatures for set NALL and time  0.5\n\n 1  1.0\n 2  2.0\n"
        " temperatures for set NALL and time  1.0\n\n 1  3.0\n 2  4.0\n")
    assert solver.read_temperatures(dat, 2).tolist() == [3.0, 4.0]


@needs_ccx
@pytest.mark.parametrize("film", [None, 5000.0], ids=["fixed bottom", "convection"])
def test_slab_matches_the_hand_calculation(slab, film, tmp_path):
    """Heat made evenly in the top layer, leaving through the bottom, sides insulated.

    The flow is one-dimensional. The film adds 1 / (h A), each passive layer adds
    t / (k A), and the source layer peaks at its top, t / (2 k A) above its base.
    """
    slab["load"].pop("film", None)
    if film:
        slab["load"]["film"] = film
    data = mesh.generate(slab)
    deck = tmp_path / "slab.inp"
    solver.write_deck(slab, data, deck)
    data["temperature"] = solver.read_temperatures(solver.run(deck), len(data["nodes"]))

    power, area = slab["load"]["power"], 4.0  # W, mm2
    rise = power / (film * area * 1e-6) if film else 0.0
    profile = [(0.0, slab["load"]["sink"] + rise)]  # (height, expected temperature)
    for layer, (_, z1) in zip(slab["layer"], params.layer_heights(slab)):
        k = slab["material"][layer["material"]]["conductivity"] / 1000  # W/(mm K)
        share = 0.5 if layer["name"] == slab["load"]["source"] else 1.0
        rise += share * power * layer["thickness"] / (k * area)
        profile.append((z1, slab["load"]["sink"] + rise))

    t_max = solver.summarise(slab, data)["t_max"]
    assert t_max == pytest.approx(profile[-1][1], rel=1e-6)

    heights = np.array([[0.3, -0.4, z] for z, _ in profile[:-1]])
    assert post.probe(data, heights) == pytest.approx([t for _, t in profile[:-1]], rel=1e-6)
