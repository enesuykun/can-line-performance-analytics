import pandas as pd
import pytest

from analysis import add_oee, oee_by


def shift(line, planned, run, ideal_cpm, total, good):
    return {"line": line, "planned_min": planned, "run_min": run, "ideal_cpm": ideal_cpm,
            "total_cans": total, "good_cans": good}


def test_add_oee_tek_vardiya():
    df = add_oee(pd.DataFrame([shift("Line 1", 480, 432, 2000, 777_600, 770_000)]))
    r = df.iloc[0]
    assert r["availability"] == pytest.approx(0.9)
    assert r["performance"] == pytest.approx(0.9)
    assert r["quality"] == pytest.approx(770_000 / 777_600)
    assert r["oee"] == pytest.approx(770_000 / (480 * 2000))


def test_oee_toplam_miktardan_hesaplanir_oranlarin_ortalamasindan_degil():
    # kısa vardiyanın OEE'si düşük; basit ortalama gerçek OEE'yi olduğundan düşük gösterir
    df = pd.DataFrame([
        shift("Line 1", 480, 480, 1000, 480_000, 480_000),  # OEE %100
        shift("Line 1", 120, 60, 1000, 60_000, 60_000),     # OEE %50
    ])
    g = oee_by(df, ["line"]).iloc[0]
    assert g["oee"] == pytest.approx(540_000 / 600_000)  # %90
    assert g["oee"] != pytest.approx(add_oee(df)["oee"].mean())  # %75


def test_oee_carpanlara_ayrilir():
    df = pd.DataFrame([
        shift("Line 1", 480, 400, 2400, 900_000, 890_000),
        shift("Line 2", 480, 450, 2200, 920_000, 905_000),
        shift("Line 2", 480, 380, 2200, 780_000, 770_000),
    ])
    g = oee_by(df, ["line"])
    assert (g["availability"] * g["performance"] * g["quality"]).tolist() == pytest.approx(g["oee"].tolist())
    assert g["oee"].tolist() == pytest.approx((g["good_cans"] / (g["planned_min"] * [2400, 2200])).tolist())
