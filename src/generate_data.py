from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START_DATE = "2026-07-01"
N_DAYS = 90
LINES = {"Line 1": 2400, "Line 2": 2200}  # ideal hız (kutu/dk)
SHIFTS = ["A", "B", "C"]
CREWS = ["Crew A", "Crew B", "Crew C", "Crew D"]
PLANNED_MIN = 480

# duruş nedeni: (vardiya başına olay sayısı, ort. süre dk, kategori)
DOWNTIME_REASONS = {
    "Bodymaker jam":          (1.2, 9,  "Mechanical"),
    "Decorator / printer":    (0.8, 14, "Mechanical"),
    "Washer temperature":     (0.3, 18, "Process"),
    "Inside spray":           (0.4, 11, "Process"),
    "Necker/flanger":         (0.5, 10, "Mechanical"),
    "Palletizer":             (0.6, 7,  "Mechanical"),
    "Coil / material wait":   (0.2, 25, "Material"),
    "Changeover":             (0.25, 45, "Planned"),
    "Quality hold":           (0.15, 30, "Quality"),
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def crew_for(day_idx, shift_idx):
    return CREWS[(day_idx // 2 + shift_idx) % len(CREWS)]


def main():
    rng = np.random.default_rng(SEED)
    dates = pd.date_range(START_DATE, periods=N_DAYS, freq="D")

    shift_rows, event_rows, sample_rows = [], [], []
    event_id = 1

    for d_idx, date in enumerate(dates):
        for s_idx, shift in enumerate(SHIFTS):
            crew = crew_for(d_idx, s_idx)
            for line, ideal_cpm in LINES.items():
                downtime = 0.0
                for reason, (lam, mean_min, category) in DOWNTIME_REASONS.items():
                    lam_adj, mean_adj = lam, mean_min
                    if line == "Line 2" and reason == "Decorator / printer" and crew == "Crew C":
                        lam_adj, mean_adj = lam * 2.5, mean_min * 1.6
                    if line == "Line 1" and reason == "Changeover" and d_idx >= 45:
                        lam_adj, mean_adj = lam * 1.8, mean_min * 1.4
                    for _ in range(rng.poisson(lam_adj)):
                        minutes = float(np.clip(rng.gamma(2.0, mean_adj / 2.0), 2, 120))
                        downtime += minutes
                        event_rows.append({
                            "event_id": event_id,
                            "date": date.date(),
                            "shift": shift,
                            "crew": crew,
                            "line": line,
                            "reason": reason,
                            "category": category,
                            "minutes": round(minutes, 1),
                        })
                        event_id += 1

                run_time = max(PLANNED_MIN - downtime, 0)
                speed_factor = np.clip(rng.normal(0.93, 0.025), 0.80, 0.99)
                total_cans = int(run_time * ideal_cpm * speed_factor)
                scrap_rate = np.clip(rng.normal(0.012, 0.004), 0.002, 0.05)
                if line == "Line 2" and crew == "Crew C":
                    scrap_rate += 0.006
                scrap_cans = int(total_cans * scrap_rate)

                shift_rows.append({
                    "date": date.date(),
                    "shift": shift,
                    "crew": crew,
                    "line": line,
                    "planned_min": PLANNED_MIN,
                    "downtime_min": round(downtime, 1),
                    "run_min": round(run_time, 1),
                    "ideal_cpm": ideal_cpm,
                    "total_cans": total_cans,
                    "scrap_cans": scrap_cans,
                    "good_cans": total_cans - scrap_cans,
                })

                # dome reversal basıncı, vardiya başına 5 kutu
                mean_psi = 93.0
                if line == "Line 2" and d_idx >= N_DAYS - 21:
                    mean_psi -= 0.12 * (d_idx - (N_DAYS - 21))
                for can_no in range(1, 6):
                    sample_rows.append({
                        "date": date.date(),
                        "shift": shift,
                        "line": line,
                        "subgroup": f"{date.date()}-{shift}",
                        "can_no": can_no,
                        "dome_reversal_psi": round(rng.normal(mean_psi, 0.7), 2),
                    })

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(shift_rows).to_csv(DATA_DIR / "production_shifts.csv", index=False)
    pd.DataFrame(event_rows).to_csv(DATA_DIR / "downtime_events.csv", index=False)
    pd.DataFrame(sample_rows).to_csv(DATA_DIR / "quality_samples.csv", index=False)
    print(f"{len(shift_rows)} shifts, {len(event_rows)} downtime events, {len(sample_rows)} samples")


if __name__ == "__main__":
    main()
