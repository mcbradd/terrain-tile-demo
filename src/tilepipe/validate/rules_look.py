"""Look rules (SPEC 10.5): LOOK-01 to LOOK-05, computed analytically from look/*.json."""
import json
import math

import numpy as np

from tilepipe.validate import common
from tilepipe.validate.registry import check_result, implements, skip

CHROMA_RAMP_MAX, CHROMA_LINE_MAX = 0.040, 0.020
CR_MIN = {"minor": 1.30, "index": 2.00, "grid": 1.20}
ADD_Y_MIN, ADD_Y_MAX, ENTITY_CR_MIN = 0.020, 0.600, 2.00
# 11.1: every entity material has this base color. Used when no entity.json has been exported yet.
ENTITY_BASE_SRGB = "#F2F0EA"


def linear(hex_srgb: str) -> np.ndarray:
    c = np.array([int(hex_srgb[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb: np.ndarray) -> float:
    return float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])


def oklch_chroma(hex_srgb: str) -> float:
    r, g, b = linear(hex_srgb)
    l = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return float(math.hypot(a, bb))


def contrast(y_hi: float, y_lo: float) -> float:
    return (max(y_hi, y_lo) + 0.05) / (min(y_hi, y_lo) + 0.05)


def nominal_shade(look: dict) -> float:
    """clamp(shade_base + shade_gain * shadeRel, 0, shade_max) at shadeRel = 1 (10.3)."""
    return min(max(look["shade_base"] + look["shade_gain"], 0.0), look["shade_max"])


def line_contrasts(look: dict) -> list[dict]:
    """Per ramp stop under nominal shading (ao = 1, shadeRel = 1): CR of the minor, index, and grid line (10.5)."""
    y_line = luminance(linear(look["line_srgb"]))
    out = []
    for stop in look["ramp"]:
        y_base = luminance(linear(stop["srgb"])) * look["k_dim"] * nominal_shade(look)
        row = {}
        for kind in CR_MIN:
            a = look[f"alpha_{kind}"]
            y = y_base * (1 - a) + y_line * a if look["mode"] == "opaque" else y_base + a * y_line
            row[kind] = contrast(y, y_base)
        out.append(row)
    return out


def terrain_luminance(look: dict, t: float) -> float:
    """Nominal luminance of the terrain at normalized height t: ramp in linear RGB, then the 10.3 lit factors."""
    ts = [s["t"] for s in look["ramp"]]
    rgb = np.array([np.interp(t, ts, [linear(s["srgb"])[i] for s in look["ramp"]]) for i in range(3)])
    return luminance(rgb) * look["k_dim"] * nominal_shade(look)


def entity_colors(ctx) -> list[str]:
    found = []
    for f in sorted((ctx.root / "dist" / "entities").glob("*/entity.json")):
        found.append(json.loads(f.read_text(encoding="utf-8"))["base_color_srgb"])
    return found or [ENTITY_BASE_SRGB]


def entity_luminance(look: dict, base_hex: str) -> float:
    """Entity at shadeRel = 1: base * 1.0 in both looks (10.6)."""
    return luminance(linear(base_hex))


@implements("LOOK-01")
def look01(ctx, scope):
    worst = max((oklch_chroma(s["srgb"]), f"{m} {s['srgb']}") for m, l in ctx.looks.items() for s in l["ramp"])
    return check_result("LOOK-01", scope, worst[0] <= CHROMA_RAMP_MAX, round(worst[0], 4), CHROMA_RAMP_MAX, "OKLCH chroma", "<=",
                        f"Desaturate ramp stop {worst[1]}.")


@implements("LOOK-02")
def look02(ctx, scope):
    worst = {k: (float("inf"), "") for k in CR_MIN}
    order_bad = []
    for mode, look in ctx.looks.items():
        for stop, row in zip(look["ramp"], line_contrasts(look)):
            for k in CR_MIN:
                if row[k] < worst[k][0]:
                    worst[k] = (row[k], f"{mode} {stop['srgb']}")
            if not row["index"] > row["minor"] > row["grid"]:
                order_bad.append(f"{mode} {stop['srgb']}")
    checks = [(f"CR, {k} line", round(worst[k][0], 3), CR_MIN[k], ">=") for k in CR_MIN]
    checks.append(("stops with index > minor > grid violated", len(order_bad), 0, "<="))
    return common.multi("LOOK-02", scope, checks,
                        "Adjust line_srgb or the alpha values so each line type reads against every ramp stop (10.5). "
                        f"Worst stops: {', '.join(v[1] for v in worst.values())}.")


@implements("LOOK-03")
def look03(ctx, scope):
    looks = [l for l in ctx.looks.values() if l["mode"] == "additive"]
    if not looks:
        return skip("LOOK-03", scope, "no additive look file")
    lo = min(luminance(linear(s["srgb"])) * l["k_dim"] * l["ao_floor"] * l["shade_base"] for l in looks for s in l["ramp"])
    hi = max(luminance(linear(s["srgb"])) * l["k_dim"] * l["shade_max"] for l in looks for s in l["ramp"])
    return common.multi("LOOK-03", scope, [("luminance, darkest stop", round(lo, 4), ADD_Y_MIN, ">="),
                                           ("luminance, brightest stop", round(hi, 4), ADD_Y_MAX, "<=")],
                        "Raise the darkest ramp stop or ao_floor, or lower the brightest stop or k_dim (10.5).")


@implements("LOOK-04")
def look04(ctx, scope):
    colors = [(f"{m} line_srgb", l["line_srgb"]) for m, l in ctx.looks.items()]
    colors += [("entity base color", c) for c in entity_colors(ctx)]
    worst = max((oklch_chroma(c), f"{what} {c}") for what, c in colors)
    return check_result("LOOK-04", scope, worst[0] <= CHROMA_LINE_MAX, round(worst[0], 4), CHROMA_LINE_MAX, "OKLCH chroma", "<=",
                        f"Desaturate {worst[1]}.")


@implements("LOOK-05")
def look05(ctx, scope):
    g = common.geo_json(ctx)
    cells = common.h_full(ctx)
    base = {}
    for f in sorted((ctx.root / "dist" / "entities").glob("*/entity.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        base[d["id"]] = d["base_color_srgb"]
    worst, where = float("inf"), ""
    for inst in common.scene_doc(ctx)["instances"]:
        r, c = inst["cell"]
        t = (float(cells[64 + r, 64 + c]) - g["h_min"]) / (g["h_max"] - g["h_min"])
        for mode, look in ctx.looks.items():
            cr = contrast(entity_luminance(look, base.get(inst["entity"], ENTITY_BASE_SRGB)),
                          terrain_luminance(look, min(max(t, 0.0), 1.0)))
            if cr < worst:
                worst, where = cr, f"{inst['entity']} at cell {r},{c} in {mode}"
    return check_result("LOOK-05", scope, worst >= ENTITY_CR_MIN, round(worst, 3), ENTITY_CR_MIN, "CR", ">=",
                        f"Move or darken terrain under the token, or lower the t limit of 7.7. Worst: {where}.")
