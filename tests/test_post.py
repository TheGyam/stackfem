import numpy as np
import pytest

from stackfem import post


def test_richardson_recovers_a_known_order():
    # f(h) = 2 + 0.5 h^2 on unequally refined meshes
    h = np.array([0.2, 0.13, 0.1])
    fit = post.richardson(h, 2 + 0.5 * h ** 2)
    assert fit["order"] == pytest.approx(2, abs=1e-6)
    assert fit["extrapolated"] == pytest.approx(2, abs=1e-9)


def test_richardson_handles_an_already_converged_result():
    fit = post.richardson([0.3, 0.2, 0.1], [5.0, 5.0, 5.0])
    assert fit["extrapolated"] == 5.0 and fit["gci"] == 0.0


def test_probe_is_exact_for_a_quadratic_field(slab_mesh):
    # Quadratic elements reproduce any quadratic field exactly, so the probe
    # must too. This also checks the mid-edge node order the probe assumes.
    _, data = slab_mesh
    x, y, z = data["nodes"].T
    field = dict(data, temperature=3 + z ** 2 - 2 * x * y + 0.5 * y)
    rng = np.random.default_rng(0)
    points = rng.uniform([-1, -1, 0], [1, 1, 1.4], size=(30, 3))
    expected = 3 + points[:, 2] ** 2 - 2 * points[:, 0] * points[:, 1] + 0.5 * points[:, 1]
    assert np.allclose(post.probe(field, points), expected, atol=1e-9)


def test_probe_outside_the_mesh_is_nan(slab_mesh):
    _, data = slab_mesh
    field = dict(data, temperature=data["nodes"][:, 2])
    assert np.isnan(post.probe(field, [[5.0, 0, 0]])[0])
