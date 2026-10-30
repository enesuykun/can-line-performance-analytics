"""İçe alınan verinin analiz öncesi kontrolü. ERP verisi asla temiz gelmez."""
import pandas as pd

KEY = ["date", "shift", "line"]
COLUMNS = ["severity", "table", "check", "count", "example"]


def _issue(issues, severity, table, check, rows):
    if len(rows):
        example = rows.head(1).to_dict("records")[0] if isinstance(rows, pd.DataFrame) else rows[0]
        issues.append({"severity": severity, "table": table, "check": check,
                       "count": len(rows), "example": str(example)})


def validate(tables, shift_minutes=480, subgroup_size=5, downtime_tolerance_min=5.0):
    """Bulunan sorunları severity (error / warning) ile bir tablo olarak döndürür."""
    issues = []
    s, e, q = tables["production_shifts"], tables["downtime_events"], tables["quality_samples"]

    for name, df in tables.items():
        nulls = df[df.isna().any(axis=1)]
        _issue(issues, "error", name, "boş değer içeren satır", nulls)

    # --- vardiya üretimi ---
    dup = s[s.duplicated(KEY, keep=False)]
    _issue(issues, "error", "production_shifts", "aynı hat/vardiya için birden fazla satır", dup)
    _issue(issues, "error", "production_shifts", f"planlanan süre vardiya süresini ({shift_minutes} dk) aşıyor "
           "(mükerrer teyit?)", s[s["planned_min"] > shift_minutes])
    _issue(issues, "error", "production_shifts", "çalışma süresi negatif veya planlanandan uzun",
           s[(s["run_min"] < 0) | (s["run_min"] > s["planned_min"])])
    _issue(issues, "error", "production_shifts", "sağlam adet negatif veya toplamdan fazla",
           s[(s["good_cans"] < 0) | (s["good_cans"] > s["total_cans"])])
    _issue(issues, "warning", "production_shifts", "üretim ideal hız kapasitesini aşıyor "
           "(ideal hız ana verisi güncel mi?)",
           s[s["total_cans"] > s["run_min"] * s["ideal_cpm"] * 1.02])

    if len(s):
        days = pd.date_range(s["date"].min(), s["date"].max(), freq="D")
        expected = pd.MultiIndex.from_product([days, sorted(s["shift"].dropna().unique()),
                                               sorted(s["line"].dropna().unique())], names=KEY)
        missing = expected.difference(pd.MultiIndex.from_frame(s[KEY]))
        _issue(issues, "warning", "production_shifts", "takvimde olup üretim kaydı olmayan vardiya",
               missing.to_frame(index=False))

    # --- duruşlar ---
    _issue(issues, "error", "downtime_events", "duruş süresi sıfır veya negatif", e[e["minutes"] <= 0])
    _issue(issues, "error", "downtime_events", "mükerrer kayıt numarası", e[e["event_id"].duplicated(keep=False)])
    orphan = e.merge(s[KEY], on=KEY, how="left", indicator=True)
    _issue(issues, "warning", "downtime_events", "üretim kaydı olmayan vardiyaya ait duruş",
           orphan[orphan["_merge"] == "left_only"].drop(columns="_merge"))

    # ERP'deki çalışma süresi ile MES duruşları birbirini tutmalı
    ev = e.groupby(KEY)["minutes"].sum().rename("event_min")
    cmp = s.set_index(KEY)[["downtime_min"]].join(ev, how="inner").fillna(0)
    gap = cmp[(cmp["downtime_min"] - cmp["event_min"]).abs() > downtime_tolerance_min]
    _issue(issues, "warning", "production_shifts", "ERP duruş süresi ile MES duruş kayıtları tutarsız",
           gap.reset_index())

    # --- kalite ---
    size = q.groupby(["line", "subgroup"]).size()
    _issue(issues, "warning", "quality_samples", f"alt grup büyüklüğü {subgroup_size} değil",
           size[size != subgroup_size].rename("n").reset_index())

    return pd.DataFrame(issues, columns=COLUMNS)


def has_errors(report):
    return bool((report["severity"] == "error").any())
