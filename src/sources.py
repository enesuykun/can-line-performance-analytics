"""ERP / MES kaynaklarından ortak şemaya veri okuma.

Her tablo bir YAML config ile tanımlanır: hangi bağlantıdan, hangi sorguyla okunacağı ve
kaynak alanların ortak şemaya nasıl dönüştürüleceği. Analiz kodu yalnızca ortak şemayı bilir;
yeni bir fabrikaya / ERP'ye kurulum sadece config yazmaktır.

Dönüşüm sırası: rename -> value_maps -> lookup -> scale -> aggregate -> derive -> şema.
"""
import os
import re
from fractions import Fraction
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent

# ortak şema: analysis.py'nin beklediği kolonlar ve tipleri
SCHEMA = {
    "production_shifts": {
        "date": "date", "shift": "str", "crew": "str", "line": "str",
        "planned_min": "float1", "downtime_min": "float1", "run_min": "float1",
        "ideal_cpm": "int", "total_cans": "int", "scrap_cans": "int", "good_cans": "int",
    },
    "downtime_events": {
        "event_id": "int", "date": "date", "shift": "str", "crew": "str", "line": "str",
        "reason": "str", "category": "str", "minutes": "float1",
    },
    "quality_samples": {
        "date": "date", "shift": "str", "line": "str", "subgroup": "str",
        "can_no": "int", "dome_reversal_psi": "float2",
    },
}
SORT_KEYS = {
    "production_shifts": ["date", "shift", "line"],
    "downtime_events": ["event_id"],
    "quality_samples": ["date", "shift", "line", "can_no"],
}

ENV_VAR = re.compile(r"\$\{(\w+)\}")
ODATA_DATE = re.compile(r"^/Date\((-?\d+)")


def expand_env(value):
    """Config içindeki ${DEGISKEN} ifadelerini ortam değişkeniyle değiştirir (şifreler config'e yazılmaz)."""
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, str):
        def sub(m):
            if m.group(1) not in os.environ:
                raise KeyError(f"Ortam değişkeni tanımlı değil: {m.group(1)}")
            return os.environ[m.group(1)]
        return ENV_VAR.sub(sub, value)
    return value


def load_config(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


# --- okuyucular ---

def read_sql(conn, query):
    from sqlalchemy import create_engine, text
    url = conn["url"]
    if url.startswith("sqlite:///") and not Path(url[len("sqlite:///"):]).is_absolute():
        url = f"sqlite:///{ROOT / url[len('sqlite:///'):]}"
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return pd.read_sql(text(query), c)
    finally:
        engine.dispose()


def read_odata(conn, entity, params=None, session=None):
    """SAP Gateway OData v2: sayfalı okur (__next), /Date(...)/ alanlarını tarihe çevirir."""
    import requests
    session = session or requests.Session()
    if conn.get("user"):
        session.auth = (conn["user"], conn.get("password", ""))
    base = conn["base_url"].rstrip("/") + "/"
    url, query = urljoin(base, entity), {"$format": "json", **(params or {})}
    rows = []
    while url:
        r = session.get(url, params=query, timeout=conn.get("timeout", 60), verify=conn.get("verify", True))
        r.raise_for_status()
        d = r.json()["d"]
        if isinstance(d, list):
            rows += d
            break
        rows += d["results"]
        # __next linki filtre ve sayfa bilgisini zaten içerir
        url, query = (urljoin(base, d["__next"]), None) if d.get("__next") else (None, None)
    df = pd.DataFrame(rows).drop(columns="__metadata", errors="ignore")
    for col in df.columns:
        s = df[col].astype(str)
        if len(s) and pd.api.types.is_string_dtype(df[col]) and s.str.match(ODATA_DATE).all():
            ms = s.str.extract(ODATA_DATE)[0].astype("int64")
            df[col] = pd.to_datetime(ms, unit="ms").dt.strftime("%Y-%m-%d")
    return df


def read_file(conn, path=None):
    p = ROOT / (path or conn["path"])
    return pd.read_excel(p) if p.suffix in (".xlsx", ".xls") else pd.read_csv(p)


def read_raw(spec, connections, session=None):
    conn = connections[spec["connection"]]
    kind = conn["type"]
    if kind == "sql":
        return read_sql(conn, spec["query"])
    if kind == "odata":
        return read_odata(conn, spec["entity"], spec.get("params"), session)
    if kind == "file":
        return read_file(conn, spec.get("path"))
    raise ValueError(f"Bilinmeyen bağlantı tipi: {kind}")


# --- dönüşüm ---

def transform(df, spec, table):
    df = df.rename(columns=spec.get("rename", {}))

    for col, mapping in spec.get("value_maps", {}).items():
        mapping = {str(k): v for k, v in mapping.items()}
        codes = df[col].dropna().astype(str)
        unknown = sorted(set(codes) - set(mapping))
        if unknown:
            raise ValueError(f"{table}.{col}: eşlemesi tanımlı olmayan kodlar {unknown}")
        df[col] = df[col].astype(str).map(mapping).where(df[col].notna())

    for col, lk in spec.get("lookup", {}).items():
        df[col] = df[lk["key"]].map(lk["values"])

    for col, factor in spec.get("scale", {}).items():
        df[col] = pd.to_numeric(df[col]) * float(Fraction(str(factor)))

    if agg := spec.get("aggregate"):
        how = {c: "sum" for c in agg.get("sum", [])} | {c: "first" for c in agg.get("first", [])}
        df = df.groupby(agg["by"], as_index=False, dropna=False).agg(how)

    for col, expr in spec.get("derive", {}).items():
        if "{" in expr:
            df[col] = [expr.format(**r) for r in df.to_dict("records")]
        else:
            df[col] = df.eval(expr)

    return to_schema(df, table)


def to_schema(df, table):
    schema = SCHEMA[table]
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise ValueError(f"{table}: eksik kolonlar {missing}")
    df = df[list(schema)].copy()
    for col, kind in schema.items():
        if kind == "date":
            df[col] = pd.to_datetime(df[col]).dt.normalize()
        elif kind == "str":
            df[col] = df[col].astype("string")
        elif kind == "int":
            df[col] = pd.to_numeric(df[col]).round().astype("Int64")
        else:  # float1 / float2
            df[col] = pd.to_numeric(df[col]).astype("float64").round(int(kind[-1]))
    return df.sort_values(SORT_KEYS[table], ignore_index=True)


def load_tables(config, tables=None, session=None):
    """Config'teki tabloları okur ve ortak şemaya çevirir. config: dosya yolu veya dict."""
    cfg = load_config(config) if isinstance(config, (str, Path)) else config
    connections = expand_env(cfg["connections"])
    out = {}
    for table, spec in cfg["tables"].items():
        if tables and table not in tables:
            continue
        out[table] = transform(read_raw(spec, connections, session), spec, table)
    return out


def write_tables(tables, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        d = df.copy()
        d["date"] = d["date"].dt.strftime("%Y-%m-%d")
        d.to_csv(out_dir / f"{name}.csv", index=False)
