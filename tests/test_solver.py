import numpy as np
import pytest

from stackfem import mesh, params, post, solver


def have_ccx():
    try:
        solver.find_ccx()
        return True
    except FileNotFoundError:
        return False


def test_heat_density_is_power_over_volume(slab):
    # 20 W in a 2 x 2 x 0.3 mm chip, in mW/mm^3
    assert solver.heat_density(slab) == pytest.approx(20_000 / 1.2)


def test_reads_the_last_printed_increment(tmp_path):
    dat = tmp_path / "job.dat"
    dat.write_text(
        " temperatures for set NALL and time  0.5\n\n 1  1.0\n 2  2.0\n"
        " temperatures for set NALL and time  1.0\n\n 1  3.0\n 2  4.0\n")
    assert solver.read_temperatures(dat, 2).tolist() == [3.0, 4.0]


@pytest.mark.skipif(not have_ccx(), reason="CalculiX (ccx) is not installed")
def test_slab_matches_the_hand_calculation(slab, tmp_path):
    """Heat made evenly in the top layer, bottom held cold, sides insulated.

    The flow is one-dimensional: each passive layer adds P t / (k A), and the
    source layer peaks at its top, P t / (2 k A) above its base. Conductivity in
    W/(m K) is W/(mm K) times 1000, hence the factor.
    """
    data = mesh.generate(slab)
    deck = tmp_path / "slab.inp"
    solver.write_deck(slab, data, deck)
    data["temperature"] = solver.read_temperatures(solver.run(deck), len(data["nodes"]))

    power, area = slab["load"]["power"], 4.0
    rise = 0.0
    profile = []  # (height, expected temperature) at each interface
    for layer, (_, z1) in zip(slab["layer"], params.layer_heights(slab)):
        k = slab["material"][layer["material"]]["conductivity"] / 1000
        share = 0.5 if layer["name"] == slab["load"]["source"] else 1.0
        rise += share * power * layer["thickness"] / (k * area)
        profile.append((z1, slab["load"]["cold_plate"] + rise))

    t_max = solver.summarise(slab, data)["t_max"]
    assert t_max == pytest.approx(profile[-1][1], rel=1e-6)

    heights = np.array([[0.3, -0.4, z] for z, _ in profile[:-1]])
    assert post.probe(data, heights) == pytest.approx([t for _, t in profile[:-1]], rel=1e-6)
