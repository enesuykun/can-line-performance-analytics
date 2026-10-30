"""ERP / MES'ten veriyi çeker, doğrular ve analizin okuduğu CSV'lere yazar.

    python src/ingest.py --config config/netsis_demo.yaml --out data/
"""
import argparse
import sys

from sources import load_tables, write_tables
from validate import has_errors, validate


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="kaynak ve alan eşleme dosyası (YAML)")
    ap.add_argument("--out", default="data", help="ortak şemadaki CSV'lerin yazılacağı klasör")
    ap.add_argument("--allow-errors", action="store_true", help="hata olsa da CSV'leri yaz")
    args = ap.parse_args(argv)

    tables = load_tables(args.config)
    for name, df in tables.items():
        print(f"{name}: {len(df)} satır")

    report = validate(tables)
    if report.empty:
        print("Doğrulama: sorun bulunmadı.")
    else:
        print("\nDoğrulama raporu:")
        print(report[["severity", "table", "check", "count"]].to_string(index=False))

    if has_errors(report) and not args.allow_errors:
        print("\nHatalar giderilmeden veri yazılmadı (--allow-errors ile zorlanabilir).", file=sys.stderr)
        return 1
    write_tables(tables, args.out)
    report.to_csv(f"{args.out}/validation_report.csv", index=False)
    print(f"\nCSV'ler {args.out}/ klasörüne yazıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
