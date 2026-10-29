# Key findings

Period: 01 Jul 2026 - 28 Sep 2026 (90 days, 2 lines, 3 shifts/day)

## Overall OEE

| Line | Availability | Performance | Quality | OEE | vs target |
|---|---|---|---|---|---|
| Line 1 | 86.9% | 93.1% | 98.8% | **80.0%** | +0.0 pts |
| Line 2 | 85.6% | 93.3% | 98.7% | **78.8%** | -1.2 pts |

## 1. Biggest losses (Pareto)

- **Line 1:** 5 of 9 reasons cause ~80% of downtime: Changeover, Decorator / printer, Bodymaker jam, Coil / material wait, Washer temperature.
- **Line 2:** 5 of 9 reasons cause ~80% of downtime: Decorator / printer, Bodymaker jam, Changeover, Washer temperature, Necker/flanger.

## 2. Line 2 decorator stops are crew-specific

- Average decorator downtime per shift: **Crew C 51.9 min** vs other crews 9.4 min (Mann-Whitney U, p = 1.8e-14).
- Line 2 OEE by crew: Crew A 79.7%, Crew B 82.3%, Crew C 72.9%, Crew D 80.4%.
- Same machine, different crews -> points to method/training (5M: Man/Method) rather than equipment. Recommended: gemba + SOP review with Crew C.

## 3. Line 1 changeovers got longer and more frequent

- First 45 days: 29 changeovers, avg 30 min.
- Last 45 days: 60 changeovers, avg 52 min (p = 0.001).
- Extra changeover time: 38 hours. Recommended: SMED study.

## 4. SPC early warning on Line 2 dome reversal pressure

- Control limits (first 60 days): LCL 92.05 / CL 93.01 / UCL 93.96 psi.
- First low-side out-of-control signal after baseline: **12 Sep 2026**. The first sampled can below LSL appeared on 17 Sep 2026, so the chart gave **5 days of early warning**.
- Cpk fell from **1.41** to **0.59** in the last 3 weeks.
- Gradual downward drift is typical of tooling wear -> act before LSL is reached.

## Daily meeting snapshot - 28 Sep 2026

- Line 1: OEE 78.4% (below target, -1.6 pts)
- Line 2: OEE 82.5% (on target, +2.5 pts)
