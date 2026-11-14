import numpy as np

from tilepipe import bake


def test_T_HEIGHT_CODEC():
    rng = np.random.default_rng(1)
    h_min, h_max = 120.5, 1890.25
    step = (h_max - h_min) / 65535
    h = rng.uniform(h_min, h_max, (64, 64))
    h[0, :2] = (h_min, h_max)
    rg = bake.encode_height(h, h_min, h_max)
    assert rg.dtype == np.uint8 and rg.shape == (64, 64, 2)
    dec = bake.decode_height(rg, h_min, h_max)
    assert np.abs(dec - h).max() <= step
    # bilinear interpolation of packed bytes vs decoded values (two steps)
    q = rg[..., 0].astype(np.float64) * 256 + rg[..., 1]
    for fx, fy in ((0.25, 0.5), (0.5, 0.5), (0.9, 0.1)):
        def lerp(a):
            top = a[:-1, :-1] * (1 - fx) + a[:-1, 1:] * fx
            bot = a[1:, :-1] * (1 - fx) + a[1:, 1:] * fx
            return top * (1 - fy) + bot * fy
        assert np.abs(lerp(h_min + q / 65535 * (h_max - h_min)) - lerp(dec)).max() <= 2 * step
        assert np.abs(lerp(dec) - lerp(h)).max() <= 2 * step


def _field(f):
    n = 1152
    r, c = np.mgrid[0:n, 0:n].astype(np.float32)
    return f(r, c).astype(np.float32)


def test_normal_unit_length():
    h = _field(lambda r, c: 5 * np.sin(c / 37) + 3 * np.cos(r / 23))
    n = bake.normals(h)
    assert n.shape == (1024, 1024, 3)
    assert np.abs(np.linalg.norm(n, axis=-1) - 1).max() < 1e-5
    assert (n[..., 1] > 0).all()
    # encoded levels: flat field encodes straight up (127.5 -> 128)
    lv = bake.nao_levels(np.zeros((1152, 1152), np.float32))
    assert [x.shape[0] for x in lv] == [1024 >> i for i in range(11)]
    assert sum(x.size for x in lv) == 5_592_404
    assert (lv[0][..., :2] == 128).all() and (lv[10][..., 3] == 255).all()


def test_AO_flat_and_pit():
    flat = bake.ao(np.full((1152, 1152), 100, np.float32))
    assert np.all(flat == 1)
    pit = _field(lambda r, c: np.where((abs(r - 576) < 6) & (abs(c - 576) < 6), -50, 0))
    a = bake.ao(pit)
    assert a[576 - 64, 576 - 64] < 0.9
    assert a.min() >= 0 and a.max() <= 1
