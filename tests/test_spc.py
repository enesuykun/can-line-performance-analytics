import numpy as np
import pandas as pd
import pytest

import analysis
from analysis import A2, DOME_LSL, SPC_BASELINE_DAYS, d2, spc_table

BASE_DAYS = SPC_BASELINE_DAYS


def samples(xbars, spread=(-1.0, -0.5, 0.0, 0.5, 1.0)):
    """Günde bir alt grup; her alt grup verilen ortalama etrafında sabit 5 ölçüm (R = 2)."""
    rows = []
    for i, xbar in enumerate(xbars):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        for k, off in enumerate(spread):
            rows.append({"date": date, "line": "Line 1", "subgroup": f"{date.date()}-A",
                         "can_no": k + 1, "dome_reversal_psi": xbar + off})
    return pd.DataFrame(rows)


def stable_base():
    # merkez çizgisinin iki yanında dönüşümlü: seri kuralı tetiklenmez
    return [93.1 if i % 2 else 92.9 for i in range(BASE_DAYS)]


def test_kontrol_limitleri_baz_donemden():
    r = spc_table(samples(stable_base() + [80.0] * 10), "Line 1")
    assert r["cl"] == pytest.approx(93.0)
    assert r["rbar"] == pytest.approx(2.0)
    assert r["ucl"] == pytest.approx(93.0 + A2 * 2.0)
    assert r["lcl"] == pytest.approx(93.0 - A2 * 2.0)
    assert r["n_base"] == BASE_DAYS


def test_kararli_surecte_sinyal_yok():
    r = spc_table(samples(stable_base() + stable_base()[:20]), "Line 1")
    assert r["alerts"] == 0
    assert r["first_alert"] is None


def test_kural1_limit_disi_nokta():
    r = spc_table(samples(stable_base() + [93.1, 92.9, 90.5, 93.1]), "Line 1")
    t = r["table"]
    assert t["rule1"].tolist().count(True) == 1
    assert t.loc[BASE_DAYS + 2, "rule1"]
    assert r["first_alert"] == pd.Timestamp("2026-01-01") + pd.Timedelta(days=BASE_DAYS + 2)


def test_seri_kurali_sekizinci_noktada_tetiklenir():
    # limitlerin içinde ama merkez çizginin altında art arda 8 nokta
    r = spc_table(samples(stable_base() + [92.7] * 8), "Line 1")
    t = r["table"]
    assert not t["rule1"].any()
    assert t["rule_run8"].tolist() == [False] * (BASE_DAYS + 7) + [True]


def test_yedi_nokta_seri_kuralini_tetiklemez():
    r = spc_table(samples(stable_base() + [92.7] * 7 + [93.3]), "Line 1")
    assert not r["table"]["rule_run8"].any()


def test_cpk_alt_spek_limitine_gore():
    r = spc_table(samples(stable_base() + [93.0] * 21), "Line 1")
    assert r["cpk_base"] == pytest.approx((93.0 - DOME_LSL) / (3 * 2.0 / d2))
    recent = np.tile([-1.0, -0.5, 0.0, 0.5, 1.0], 21) + 93.0
    assert r["cpk_recent"] == pytest.approx((93.0 - DOME_LSL) / (3 * recent.std(ddof=1)))


def test_spc_grafigi_kaydedilir(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "CHARTS", tmp_path)
    analysis.spc_analysis(samples(stable_base() + [92.7] * 8), "Line 1")
    assert (tmp_path / "05_spc_line1.png").exists()
