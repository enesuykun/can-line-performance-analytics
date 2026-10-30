"""Ortak şemadaki CSV'lerden Netsis tarzı örnek bir ERP + MES veritabanı (SQLite) üretir.

Tablo ve alan adları kurgusaldır; gerçek bir Netsis kurulumunun tablolarını temsil etmez.
Amaç, ERP verisinin tipik "dağınıklığını" taklit etmektir:
  - üretim teyitleri vardiya değil iş emri bazında (bir vardiyada 1-2 iş emri)
  - miktarlar bin adet, duruş süreleri saniye cinsinden
  - hat, vardiya, ekip ve duruş nedeni kod olarak tutulur
  - ideal hız hat ana verisinde, duruş nedeni açıklamaları ayrı tabloda

--dirty ile veriye tipik ERP hataları eklenir (mükerrer teyit, negatif süre, eksik kayıt).

    python src/build_demo_erp.py [--dirty] [--out data/demo_erp.sqlite]
"""
import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LINE_CODES = {"Line 1": "H01", "Line 2": "H02"}
SHIFT_CODES = {"A": 1, "B": 2, "C": 3}
CREW_CODES = {"Crew A": "E1", "Crew B": "E2", "Crew C": "E3", "Crew D": "E4"}


def build(out, dirty=False, seed=7):
    rng = np.random.default_rng(seed)
    shifts = pd.read_csv(DATA / "production_shifts.csv")
    events = pd.read_csv(DATA / "downtime_events.csv")
    quality = pd.read_csv(DATA / "quality_samples.csv")

    lines = (shifts.groupby("line")["ideal_cpm"].first().reset_index()
             .assign(HAT_KODU=lambda d: d["line"].map(LINE_CODES))
             .rename(columns={"line": "HAT_ADI", "ideal_cpm": "IDEAL_HIZ_DK"}))

    reasons = (events.groupby("reason")["category"].first().reset_index()
               .rename(columns={"reason": "ACIKLAMA", "category": "KATEGORI"}))
    reasons.insert(0, "NEDEN_KODU", [f"D{i:02d}" for i in range(1, len(reasons) + 1)])
    reason_codes = dict(zip(reasons["ACIKLAMA"], reasons["NEDEN_KODU"]))

    # vardiya -> 1 veya 2 iş emri teyidi; miktarlar tam sayı olarak bölünür
    conf = []
    order_no = 26000
    for r in shifts.itertuples():
        n = rng.choice([1, 2], p=[0.6, 0.4])
        frac = rng.uniform(0.3, 0.7) if n == 2 else 1.0
        cans = [int(r.total_cans * frac)] + ([r.total_cans - int(r.total_cans * frac)] if n == 2 else [])
        scrap = [int(r.scrap_cans * frac)] + ([r.scrap_cans - int(r.scrap_cans * frac)] if n == 2 else [])
        run = [round(r.run_min * frac, 1)] + ([round(r.run_min - round(r.run_min * frac, 1), 1)] if n == 2 else [])
        plan = [round(r.planned_min * frac, 1)] + ([round(r.planned_min - round(r.planned_min * frac, 1), 1)] if n == 2 else [])
        for i in range(n):
            order_no += 1
            conf.append({
                "TEYIT_NO": len(conf) + 1, "ISEMRI_NO": f"IE{order_no}", "TEYIT_TARIHI": r.date,
                "VARDIYA": SHIFT_CODES[r.shift], "EKIP_KODU": CREW_CODES[r.crew], "HAT_KODU": LINE_CODES[r.line],
                "PLANLANAN_SURE_DK": plan[i], "CALISMA_SURE_DK": run[i],
                "URETIM_BIN_ADET": cans[i] / 1000, "FIRE_BIN_ADET": scrap[i] / 1000,
            })
    conf = pd.DataFrame(conf)

    mes = pd.DataFrame({
        "KAYIT_NO": events["event_id"], "VARDIYA_TARIHI": events["date"],
        "VARDIYA": events["shift"].map(SHIFT_CODES), "EKIP_KODU": events["crew"].map(CREW_CODES),
        "HAT_KODU": events["line"].map(LINE_CODES), "NEDEN_KODU": events["reason"].map(reason_codes),
        "SURE_SN": (events["minutes"] * 60).round().astype(int),
    })

    lab = pd.DataFrame({
        "OLCUM_TARIHI": quality["date"], "VARDIYA": quality["shift"].map(SHIFT_CODES),
        "HAT_KODU": quality["line"].map(LINE_CODES), "KARAKTERISTIK": "DOME_REV_PSI",
        "NUMUNE_SIRA": quality["can_no"], "DEGER": quality["dome_reversal_psi"],
    })

    if dirty:
        conf = pd.concat([conf, conf.iloc[[100]].assign(TEYIT_NO=len(conf) + 1)], ignore_index=True)  # mükerrer teyit
        mes.loc[5, "SURE_SN"] = -mes.loc[5, "SURE_SN"]                                            # negatif süre
        first = conf.iloc[200]
        conf = conf[~((conf["TEYIT_TARIHI"] == first["TEYIT_TARIHI"]) & (conf["VARDIYA"] == first["VARDIYA"])
                      & (conf["HAT_KODU"] == first["HAT_KODU"]))]                                  # eksik vardiya
        lab = lab.drop(index=lab.index[10])                                                        # eksik ölçüm

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    with sqlite3.connect(out) as con:
        lines[["HAT_KODU", "HAT_ADI", "IDEAL_HIZ_DK"]].to_sql("HAT_TANIM", con, index=False)
        conf.to_sql("URETIM_TEYIT", con, index=False)
        reasons.to_sql("DURUS_NEDEN", con, index=False)
        mes.to_sql("MES_DURUS", con, index=False)
        lab.to_sql("KALITE_OLCUM", con, index=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "demo_erp.sqlite"))
    ap.add_argument("--dirty", action="store_true", help="tipik ERP veri hatalarını ekle")
    args = ap.parse_args()
    print(f"Örnek ERP veritabanı: {build(args.out, args.dirty)}")


if __name__ == "__main__":
    main()
