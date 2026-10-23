import copy

import numpy as np
import pytest

from stackfem import mesh, quality, solver

# CalculiX's C3D10 mid-edge nodes 4..9 sit on these corner pairs.
CCX_EDGES = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]


def tet_volumes(nodes, conn):
    a, b, c, d = (nodes[conn[:, i] - 1] for i in range(4))
    return np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a)) / 6


def test_every_layer_is_meshed_and_fills_its_box(slab_mesh):
    p, data = slab_mesh
    for layer in p["layer"]:
        conn = data["elements"][layer["name"]]
        volume = tet_volumes(data["nodes"], conn)
        assert (volume > 0).all(), "an element is inverted"
        expected = layer["size"][0] * layer["size"][1] * layer["thickness"]
        assert volume.sum() == pytest.approx(expected, rel=1e-9)


def test_thin_layer_gets_the_finer_mesh(slab_mesh):
    p, data = slab_mesh
    count = {name: len(conn) for name, conn in data["elements"].items()}
    density = {l["name"]: count[l["name"]] / l["thickness"] for l in p["layer"]}
    assert density["joint"] > 5 * density["base"]


def test_node_order_matches_calculix(slab_mesh):
    _, data = slab_mesh
    nodes = data["nodes"]
    conn = np.vstack(list(data["elements"].values()))[:, solver.GMSH_TO_CCX] - 1
    for k, (a, b) in enumerate(CCX_EDGES):
        middle = (nodes[conn[:, a]] + nodes[conn[:, b]]) / 2
        assert np.allclose(nodes[conn[:, 4 + k]], middle)


def test_cold_nodes_are_the_bottom_face(slab_mesh):
    _, data = slab_mesh
    z = data["nodes"][:, 2]
    assert np.allclose(z[data["cold"] - 1], 0)
    assert len(data["cold"]) == np.isclose(z, 0).sum()


def test_quality_report_covers_every_layer(slab_mesh):
    p, data = slab_mesh
    assert set(data["quality"]) == {l["name"] for l in p["layer"]}
    assert all(r["min_sicn"] > 0 for r in data["quality"].values())


def test_quality_check_stops_a_poor_mesh(slab):
    p = copy.deepcopy(slab)
    p["quality"]["min_sicn"] = 0.99  # no real mesh is this good
    with pytest.raises(quality.QualityError, match="worst SICN"):
        mesh.generate(p)


def test_save_and_load_round_trip(slab_mesh, tmp_path):
    _, data = slab_mesh
    mesh.save(data, tmp_path / "m.npz")
    back = mesh.load(tmp_path / "m.npz")
    assert np.array_equal(back["nodes"], data["nodes"])
    assert list(back["elements"]) == list(data["elements"])
