"""Can Line Performance - interaktif dashboard.

Çalıştırma: streamlit run app.py
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from analysis import (DOME_LSL, OEE_TARGET, add_oee, decorator_crew_test,  # noqa: E402
                      load, oee_by, spc_table)

LINE_COLORS = {"Line 1": "#2a78d6", "Line 2": "#eb6834"}
C_REF = "#8c8c8c"        # hedef / kontrol limitleri
C_CRITICAL = "#d03b3b"   # SPC sinyali ve spek limiti
DIVERGING = [[0, "#d03b3b"], [0.5, "#f0efec"], [1, "#2a78d6"]]  # hedefin altı / üstü

st.set_page_config(page_title="Can Line Performance", page_icon="🥫", layout="wide")


@st.cache_data
def get_data():
    shifts, events, quality = load()
    return add_oee(shifts), events, quality


@st.cache_data
def get_spc(quality, line):
    return spc_table(quality, line)


def layout(fig, height=380, hovermode="x unified", right=10, **kw):
    fig.update_layout(height=height, margin=dict(l=10, r=right, t=30, b=10),
                      legend=dict(orientation="h", y=1.08, x=0), hovermode=hovermode, **kw)
    return fig


shifts, events, quality = get_data()

# --- filtreler ---
st.sidebar.header("Filtreler")
d_min, d_max = shifts["date"].min().date(), shifts["date"].max().date()
period = st.sidebar.date_input("Tarih aralığı", (d_min, d_max), min_value=d_min, max_value=d_max)
lines = st.sidebar.multiselect("Hat", sorted(shifts["line"].unique()), default=sorted(shifts["line"].unique()))
crews = st.sidebar.multiselect("Ekip", sorted(shifts["crew"].unique()), default=sorted(shifts["crew"].unique()))
shift_ids = st.sidebar.multiselect("Vardiya", sorted(shifts["shift"].unique()), default=sorted(shifts["shift"].unique()))

if len(period) != 2 or not (lines and crews and shift_ids):
    st.warning("Her filtreden en az bir değer ve tam bir tarih aralığı seçin.")
    st.stop()

start, end = pd.Timestamp(period[0]), pd.Timestamp(period[1])


def apply_filters(df):
    return df[df["date"].between(start, end) & df["line"].isin(lines)
              & df["crew"].isin(crews) & df["shift"].isin(shift_ids)]


s, e = apply_filters(shifts), apply_filters(events)

st.title("Can Line Performance")
st.caption(f"{start:%d %b %Y} – {end:%d %b %Y} · {len(s)} vardiya · "
           f"OEE hedefi %{OEE_TARGET * 100:.0f} · veriler sentetiktir")

# --- KPI satırı ---
kpi = oee_by(s, ["line"]).set_index("line")
cols = st.columns(len(kpi) * 2)
for i, (line, r) in enumerate(kpi.iterrows()):
    cols[2 * i].metric(f"{line} OEE", f"%{r.oee * 100:.1f}",
                       f"{(r.oee - OEE_TARGET) * 100:+.1f} puan hedefe göre")
    cols[2 * i + 1].markdown(
        f"**{line}**  \nKullanılabilirlik %{r.availability * 100:.1f}  \n"
        f"Performans %{r.performance * 100:.1f}  \nKalite %{r.quality * 100:.1f}")

tab_oee, tab_pareto, tab_crew, tab_spc, tab_data = st.tabs(
    ["OEE trendi", "Duruş Pareto", "Ekip karşılaştırması", "SPC", "Veri"])

# --- OEE trendi ---
with tab_oee:
    grain = st.radio("Zaman birimi", ["Haftalık", "Günlük"], horizontal=True)
    t = s.assign(period=s["date"].dt.to_period("W").dt.start_time if grain == "Haftalık" else s["date"])
    trend = oee_by(t, ["period", "line"])
    fig = go.Figure()
    for line in lines:
        d = trend[trend["line"] == line]
        fig.add_scatter(x=d["period"], y=d["oee"] * 100, name=line, mode="lines+markers",
                        line=dict(color=LINE_COLORS[line], width=2), marker=dict(size=8),
                        customdata=d[["availability", "performance", "quality"]] * 100,
                        hovertemplate="OEE %{y:.1f}% · K %{customdata[0]:.1f}% · "
                                      "P %{customdata[1]:.1f}% · Q %{customdata[2]:.1f}%")
    fig.add_hline(OEE_TARGET * 100, line=dict(color=C_REF, dash="dash", width=1),
                  annotation_text=f"Hedef %{OEE_TARGET * 100:.0f}", annotation_position="top left")
    st.plotly_chart(layout(fig, yaxis_title="OEE (%)"), width="stretch")
    if grain == "Haftalık":
        st.caption("Dönem başı ve sonundaki eksik haftalar daha az vardiya içerir.")

# --- Pareto ---
with tab_pareto:
    if e.empty:
        st.info("Seçili filtrelerde duruş kaydı yok.")
    else:
        pcols = st.columns(len(lines))
        for col, line in zip(pcols, lines):
            p = (e[e["line"] == line].groupby("reason")["minutes"].agg(["sum", "count"])
                 .sort_values("sum", ascending=False))
            if p.empty:
                col.info(f"{line}: duruş yok")
                continue
            p["cum_pct"] = p["sum"].cumsum() / p["sum"].sum() * 100
            vital = (p["cum_pct"].shift(fill_value=0) < 80).to_numpy()
            fig = go.Figure(go.Bar(
                y=p.index, x=p["sum"] / 60, orientation="h",
                marker=dict(color=[LINE_COLORS[line] if v else C_REF for v in vital]),
                text=[f"kümülatif %{c:.0f}" for c in p["cum_pct"]], textposition="outside",
                customdata=p[["count", "cum_pct"]],
                hovertemplate="%{y}<br>%{x:.1f} saat · %{customdata[0]} duruş · "
                              "kümülatif %{customdata[1]:.0f}%<extra></extra>"))
            fig.update_yaxes(autorange="reversed")
            col.markdown(f"**{line}** – {int(vital.sum())}/{len(p)} neden kaybın ~%80'i")
            col.plotly_chart(layout(fig, height=360, xaxis_title="Duruş (saat)", hovermode="closest",
                                    xaxis_range=[0, p["sum"].max() / 60 * 1.35]),
                             width="stretch")

# --- ekip karşılaştırması ---
with tab_crew:
    crew = oee_by(s, ["line", "crew"]).pivot(index="line", columns="crew", values="oee") * 100
    span = max(abs(crew.values - OEE_TARGET * 100).max(), 1)
    fig = go.Figure(go.Heatmap(
        z=crew.values, x=crew.columns, y=crew.index, colorscale=DIVERGING,
        zmin=OEE_TARGET * 100 - span, zmax=OEE_TARGET * 100 + span,
        text=[[f"%{v:.1f}" for v in row] for row in crew.values], texttemplate="%{text}",
        xgap=2, ygap=2, colorbar=dict(title="OEE %"),
        hovertemplate="%{y} · %{x}<br>OEE %{z:.1f}%<extra></extra>"))
    st.plotly_chart(layout(fig, height=260, hovermode="closest"), width="stretch")
    st.caption(f"Renk, %{OEE_TARGET * 100:.0f} hedefinden sapmayı gösterir: kırmızı altında, mavi üstünde.")

    if "Line 2" in lines and s["crew"].nunique() > 1 and "Crew C" in crews:
        t = decorator_crew_test(s, e)
        st.subheader("Hat 2 – dekoratör duruşu ekibe bağlı mı?")
        c1, c2, c3 = st.columns(3)
        c1.metric("Crew C, dk/vardiya", f"{t['crew_c_mean']:.1f}")
        c2.metric("Diğer ekipler, dk/vardiya", f"{t['others_mean']:.1f}")
        c3.metric("Mann-Whitney U p-değeri", f"{t['p_value']:.1e}")
        fig = go.Figure(go.Bar(x=t["by_crew"].index, y=t["by_crew"].values,
                               marker_color=LINE_COLORS["Line 2"],
                               hovertemplate="%{x}: %{y:.1f} dk/vardiya<extra></extra>"))
        st.plotly_chart(layout(fig, height=260, yaxis_title="Dekoratör duruşu (dk/vardiya)",
                               hovermode="closest"), width="stretch")

# --- SPC ---
with tab_spc:
    line = st.radio("Hat", sorted(quality["line"].unique()), index=1, horizontal=True, key="spc_line")
    r = get_spc(quality, line)
    sg = r["table"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cpk (baz dönem)", f"{r['cpk_base']:.2f}")
    c2.metric("Cpk (son 3 hafta)", f"{r['cpk_recent']:.2f}", f"{r['cpk_recent'] - r['cpk_base']:+.2f}")
    c3.metric("İlk aşağı yönlü sinyal", f"{r['first_alert']:%d %b}" if r["first_alert"] is not None else "yok")
    if pd.notna(r["first_out_of_spec"]):
        lead = (r["first_out_of_spec"] - r["first_alert"]).days if r["first_alert"] is not None else None
        c4.metric("İlk spek dışı kutu", f"{r['first_out_of_spec']:%d %b}",
                  f"{lead} gün önceden uyarı" if lead else None, delta_color="off")
    else:
        c4.metric("İlk spek dışı kutu", "yok")

    fig = go.Figure()
    x = sg["subgroup"]
    fig.add_vrect(x0=x.iloc[0], x1=x.iloc[r["n_base"] - 1], fillcolor=C_REF, opacity=0.08, line_width=0,
                  annotation_text="Faz I baz dönem", annotation_position="top left")
    fig.add_scatter(x=x, y=sg["xbar"], name="X-bar", mode="lines+markers",
                    line=dict(color=LINE_COLORS[line], width=2), marker=dict(size=4),
                    hovertemplate="%{x}<br>X-bar %{y:.2f} psi<extra></extra>")
    a = sg[sg["alert"]]
    fig.add_scatter(x=a["subgroup"], y=a["xbar"], name="Kontrol dışı sinyal", mode="markers",
                    marker=dict(color=C_CRITICAL, size=9, symbol="x"),
                    customdata=a[["rule1", "rule_run8"]].replace({True: "evet", False: "hayır"}),
                    hovertemplate="%{x}<br>Kural 1: %{customdata[0]} · 8'li seri: %{customdata[1]}<extra></extra>")
    for y, lab, dash in [(r["ucl"], "UCL", "dash"), (r["cl"], "CL", "solid"), (r["lcl"], "LCL", "dash")]:
        fig.add_hline(y, line=dict(color=C_REF, dash=dash, width=1),
                      annotation_text=f"{lab} {y:.2f}", annotation_position="right")
    fig.add_hline(DOME_LSL, line=dict(color=C_CRITICAL, dash="dot", width=1.5),
                  annotation_text=f"LSL {DOME_LSL:.0f}", annotation_position="right")
    fig.update_xaxes(type="category", showticklabels=False, title="Alt grup (vardiya)")
    st.plotly_chart(layout(fig, height=400, yaxis_title="Dome reversal basıncı X-bar (psi)",
                           hovermode="closest", right=80), width="stretch")

    fig = go.Figure(go.Scatter(x=x, y=sg["r"], mode="lines", line=dict(color=C_REF, width=1.5),
                               name="R", hovertemplate="%{x}<br>R %{y:.2f} psi<extra></extra>"))
    fig.add_hline(r["rbar"], line=dict(color=C_REF, width=1), annotation_text=f"R̄ {r['rbar']:.2f}",
                  annotation_position="right")
    fig.update_xaxes(type="category", showticklabels=False)
    st.plotly_chart(layout(fig, height=200, yaxis_title="Aralık R (psi)", hovermode="closest", right=80),
                    width="stretch")

# --- veri ---
with tab_data:
    view = s[["date", "line", "shift", "crew", "availability", "performance", "quality", "oee",
              "downtime_min", "good_cans"]].sort_values(["date", "line", "shift"])
    st.dataframe(view, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="percent")
                                for c in ["availability", "performance", "quality", "oee"]})
    st.download_button("CSV indir", view.to_csv(index=False).encode("utf-8"),
                       "vardiya_oee.csv", "text/csv")
