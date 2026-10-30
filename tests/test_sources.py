import sqlite3

import pandas as pd
import pytest

import analysis
import build_demo_erp
from ingest import main as ingest
from sources import ROOT, expand_env, load_tables, to_schema, transform
from validate import has_errors, validate

NETSIS = ROOT / "config" / "netsis_demo.yaml"
SAP = ROOT / "config" / "sap_s4_example.yaml"


def demo_config(db):
    import yaml
    cfg = yaml.safe_load(NETSIS.read_text(encoding="utf-8"))
    for c in cfg["connections"].values():
        c["url"] = f"sqlite:///{db}"
    return cfg


@pytest.fixture(scope="module")
def clean_db(tmp_path_factory):
    return build_demo_erp.build(tmp_path_factory.mktemp("erp") / "erp.sqlite")


@pytest.fixture(scope="module")
def dirty_db(tmp_path_factory):
    return build_demo_erp.build(tmp_path_factory.mktemp("erp") / "erp.sqlite", dirty=True)


def test_ornek_erp_dagınık_yapida(clean_db):
    with sqlite3.connect(clean_db) as con:
        conf = pd.read_sql("SELECT * FROM URETIM_TEYIT", con)
        mes = pd.read_sql("SELECT * FROM MES_DURUS", con)
    assert len(conf) > 540                      # vardiya değil iş emri bazında
    assert conf["URETIM_BIN_ADET"].max() < 2000  # bin adet
    assert set(conf["HAT_KODU"]) == {"H01", "H02"}
    assert mes["SURE_SN"].median() > 60          # saniye


def test_erpden_okunan_veri_orijinal_ile_ayni(clean_db):
    tables = load_tables(demo_config(clean_db))
    for name, ref in zip(["production_shifts", "downtime_events", "quality_samples"], analysis.load()):
        pd.testing.assert_frame_equal(tables[name], to_schema(ref, name))
    assert validate(tables).empty


def test_kirli_veride_hatalar_yakalanir(dirty_db):
    report = validate(load_tables(demo_config(dirty_db)))
    checks = set(report["check"])
    assert has_errors(report)
    assert any("vardiya süresini" in c for c in checks)          # mükerrer teyit
    assert "duruş süresi sıfır veya negatif" in checks
    assert "takvimde olup üretim kaydı olmayan vardiya" in checks
    assert any("alt grup büyüklüğü" in c for c in checks)


def test_ingest_hatali_veriyi_yazmaz(dirty_db, tmp_path, monkeypatch, capsys):
    import yaml
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.safe_dump(demo_config(dirty_db)), encoding="utf-8")
    assert ingest(["--config", str(cfg), "--out", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out" / "production_shifts.csv").exists()


def test_ingest_ciktisi_analiz_tarafindan_okunur(clean_db, tmp_path):
    import yaml
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.safe_dump(demo_config(clean_db)), encoding="utf-8")
    assert ingest(["--config", str(cfg), "--out", str(tmp_path)]) == 0
    for got, ref in zip(analysis.load(tmp_path), analysis.load()):
        pd.testing.assert_frame_equal(got, ref, check_dtype=False)  # 480 vs 480.0


def test_eslemesi_olmayan_kod_hata_verir():
    df = pd.DataFrame({"line": ["H01", "H09"]})
    with pytest.raises(ValueError, match="H09"):
        transform(df, {"value_maps": {"line": {"H01": "Line 1"}}}, "quality_samples")


def test_sifreler_ortam_degiskeninden(monkeypatch):
    monkeypatch.setenv("ERP_PASS", "gizli")
    assert expand_env({"a": ["x-${ERP_PASS}"]}) == {"a": ["x-gizli"]}
    monkeypatch.delenv("ERP_PASS")
    with pytest.raises(KeyError, match="ERP_PASS"):
        expand_env("${ERP_PASS}")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSapSession:
    """İki sayfalık OData v2 cevabı: aynı vardiyada iki iş emri teyidi."""
    auth = None

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        row = {"__metadata": {}, "PostingDate": "/Date(1782864000000)/", "WorkCenter": "CANL02",
               "ShiftDefinition": "1", "ShiftGroup": "G3"}
        if len(self.calls) == 1:
            return FakeResponse({"d": {"results": [row | {"ConfirmationYieldQuantity": 500000,
                                                          "ConfirmationScrapQuantity": 6000,
                                                          "OpConfirmedWorkQuantity1": 230.0}],
                                       "__next": "ProdnOrdConf2?$skiptoken=1"}})
        return FakeResponse({"d": {"results": [row | {"ConfirmationYieldQuantity": 400000,
                                                      "ConfirmationScrapQuantity": 5000,
                                                      "OpConfirmedWorkQuantity1": 190.5}]}})


def test_sap_odata_sayfalama_ve_vardiyaya_toplama(monkeypatch):
    for k, v in {"SAP_HOST": "sap.example", "SAP_USER": "okuma", "SAP_PASSWORD": "x",
                 "MES_DB_URL": "sqlite://"}.items():
        monkeypatch.setenv(k, v)
    session = FakeSapSession()
    df = load_tables(SAP, tables=["production_shifts"], session=session)["production_shifts"]

    assert len(session.calls) == 2
    assert session.calls[0][0].endswith("/API_PROD_ORDER_CONFIRMATION_2_SRV/ProdnOrdConf2")
    assert "$filter" in session.calls[0][1] and session.calls[1][1] is None
    assert session.auth == ("okuma", "x")

    r = df.iloc[0]
    assert len(df) == 1
    assert (r["date"], r["shift"], r["crew"], r["line"]) == (pd.Timestamp("2026-07-01"), "A", "Crew C", "Line 2")
    assert (r["good_cans"], r["scrap_cans"], r["total_cans"]) == (900_000, 11_000, 911_000)
    assert r["run_min"] == pytest.approx(420.5)
    assert r["downtime_min"] == pytest.approx(59.5)
    assert r["ideal_cpm"] == 2200
