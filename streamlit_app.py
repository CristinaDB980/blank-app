import streamlit as st
import re
import json, gzip, re, time, hashlib
from datetime import date

st.set_page_config(page_title="RPA Stage-Gate-Modell", layout="wide", initial_sidebar_state="expanded")

st.title("🧾 RPA-Checkliste – Stage-Gate-Modell")
st.markdown("Nur wenn ein Abschnitt abgeschlossen ist, wird der nächste sichtbar.")
# SVG immer in Spaltenbreite skalieren
st.markdown("""
<style>
[data-testid="stGraphVizChart"] svg {
  width:100% !important;      /* statt width:auto */
  height:auto !important;
  max-width:100% !important;
}
[data-testid="stGraphVizChart"] { overflow-x: hidden !important; }  /* kein horizontaler Cut */
div[data-testid="column"] { overflow: visible !important; }
</style>
""", unsafe_allow_html=True)


with st.sidebar:
    st.markdown("### 💾 Zwischenstand")

    # Einmalige State-Defaults
    st.session_state.setdefault("_uploader_key", "uploader_v1")
    st.session_state.setdefault("_loaded_sig", None)

    # Nur erlaubte Keys sichern
    STATUS_KEYS = {
        "phase0_complete","gate1_complete","phase1_complete","gate2_complete",
        "phase2_complete","gate3_complete","phase3_complete","gate4_complete",
        "phase4_complete","gate5_complete","phase5_complete",
        "postimpl_complete","all_complete",
        "prozessname","prozesseigentuemer",
        # Post-Impl Inputs dürfen gespeichert werden (nicht die Anzeige-Flags)
        "pic_err_rate","pic_exec_min","pic_fix_min","pic_save_min",
        "pic_runs_week","pic_hourly_cost",
    }
    PREFIXES = ("g1_", "p1_", "g2_", "p2_", "g3_", "p3_", "g4_", "p4_", "g5_", "p5_")

    def _slug(s: str) -> str:
        s = (s or "Unbenannter Prozess").strip()
        s = re.sub(r"[^\w\s-]", "", s); s = re.sub(r"\s+", "_", s)
        return s[:80] or "Unbenannter_Prozess"

    def make_save_state() -> dict:
        out = {}
        for k, v in st.session_state.items():
            if (k in STATUS_KEYS) or (isinstance(k, str) and k.startswith(PREFIXES)):
                # temporäre/anzeige-Flags NICHT speichern
                if k in ("pic_show_chart", "_loaded_sig", "_uploader_key"):
                    continue
                if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                    out[k] = v
        return out

    safe_name = _slug(st.session_state.get("prozessname", "Unbenannter Prozess"))
    base_filename = f"{safe_name}_rpa_stagegate_{date.today().isoformat()}"

    # Export (minifiziert wäre schneller, hier okay)
    state_json = json.dumps(make_save_state(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    st.download_button("💾 Zwischenstand speichern (JSON)", data=state_json,
                       file_name=f"{base_filename}.json", mime="application/json", key="dl_json_fast")

    state_gz = gzip.compress(state_json, compresslevel=1)
    st.download_button("💾 Zwischenstand speichern (kompakt .json.gz)", data=state_gz,
                       file_name=f"{base_filename}.json.gz", mime="application/gzip", key="dl_gz_fast")

    st.markdown("---")

    # ⬇️ Dynamischer Key, damit wir den Uploader nach dem Laden „leeren“ können
    uploaded = st.file_uploader("📤 Zwischenstand laden (.json / .json.gz)",
                                type=["json","gz"], key=st.session_state["_uploader_key"])

    # Optionaler Button: Datei entfernen/Zurücksetzen
    if uploaded is not None:
        if st.button("Datei entfernen", key="btn_clear_upload"):
            st.session_state["_uploader_key"] = f"uploader_v1_{int(time.time())}"
            st.session_state["_loaded_sig"] = None
            st.success("Dateiauswahl zurückgesetzt.")
            st.rerun()

# ==== Lade-Logik (außerhalb der Sidebar, wie bei dir) ====
def _file_signature(file_obj) -> tuple[str, bytes]:
    data = file_obj.getvalue()
    # schnelle, eindeutige Signatur (Name + Größe + Hash)
    sig = f"{file_obj.name}:{len(data)}:{hashlib.md5(data).hexdigest()}"
    return sig, data

if 'uploaded' in locals() and uploaded is not None:
    try:
        sig, data_bytes = _file_signature(uploaded)
        # Nur verarbeiten, wenn neu (verhindert Endlos-Reloads)
        if st.session_state.get("_loaded_sig") != sig:
            # GZip auto-erkennen
            if uploaded.name.endswith(".gz") or (len(data_bytes)>=2 and data_bytes[0]==0x1F and data_bytes[1]==0x8B):
                data_bytes = gzip.decompress(data_bytes)
            text = data_bytes.decode("utf-8", errors="strict")
            loaded = json.loads(text)
            if not isinstance(loaded, dict):
                st.error("Ungültiges Format: Erwartet JSON-Objekt (Key→Value).")
            else:
                # Whitelist anwenden
                def _is_allowed(k: str) -> bool:
                    return (k in STATUS_KEYS) or any(k.startswith(p) for p in PREFIXES)
                cleaned = {str(k): v for k, v in loaded.items() if _is_allowed(str(k))}

                # evtl. alte Keys auf neue mappen (optional)
                mapping = {
                    "gate3_complet": "gate3_complete",  # Tippfehler alt → neu
                    "stage1_complete": "gate1_complete",
                    "stage2_complete": "phase1_complete",
                }
                for old, new in mapping.items():
                    if old in cleaned and new not in cleaned:
                        cleaned[new] = cleaned.pop(old)

                # Kritische UI-Keys entfernen (Sicherheit)
                for bad in ("uploader", "uploader_fast", "dl_json", "dl_gz", "dl_json_fast", "dl_gz_fast"):
                    st.session_state.pop(bad, None)

                # State übernehmen
                st.session_state.update(cleaned)

                # Merken, dass diese Datei geladen wurde
                st.session_state["_loaded_sig"] = sig

                # Uploader „leeren“, damit nicht bei jedem Re-Run erneut geladen wird
                st.session_state["_uploader_key"] = f"uploader_v1_{int(time.time())}"

                st.success(f"Zwischenstand geladen ({len(cleaned)} Felder).")
                st.rerun()
        else:
            # bereits geladene Datei – nichts mehr tun
            pass
    except gzip.BadGzipFile:
        st.error("GZip-Datei fehlerhaft. Bitte gültiges .json oder korrektes .json.gz laden.")
    except UnicodeDecodeError:
        st.error("Datei ist nicht UTF-8. Bitte die original erzeugte JSON verwenden (nicht in Excel öffnen/speichern).")
    except json.JSONDecodeError as e:
        st.error(f"JSON nicht lesbar: Zeile {e.lineno}, Spalte {e.colno}.")
    except Exception as e:
        st.error(f"Unerwarteter Fehler beim Laden: {e}")

# === SESSION STATE ===
for key in ["phase0_complete", "gate1_complete", "phase1_complete", "gate2_complete", "phase2_complete", "gate3_complete",
    "phase3_complete",  "gate4_complete", "phase4_complete", "gate5_complete", "phase5_complete", "postimpl_complete",  "all_complete"]:
        st.session_state.setdefault(key, False)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# === Prozessübersicht" ===
try:
    from graphviz import Digraph
    GV = True
except Exception:
    GV = False

# Schritte & Labels 
_STEPS_V = [
    {"type":"start","key":"start","label":"Potenzieller\nProzess"},
    {"type":"gate" ,"key":"g1","label":"Gate 1","xlabel":"RPA-Eignungstest"},
    {"type":"phase","key":"p1","label":"Phase 1\nProzessanalyse-/\nvorbereitung"},
    {"type":"gate" ,"key":"g2","label":"Gate 2","xlabel":"RPA-Score"},
    {"type":"phase","key":"p2","label":"Phase 2\nDesign-/\nEntwicklungsphase"},
    {"type":"gate" ,"key":"g3","label":"Gate 3","xlabel":"Prototyp-Freigabe"},
    {"type":"phase","key":"p3","label":"Phase 3\nTestphase"},
    {"type":"gate" ,"key":"g4","label":"Gate 4","xlabel":"Produktions-Freigabe"},
    {"type":"phase","key":"p4","label":"Phase 4\nImplementierungsphase /\nGo Live"},
    {"type":"gate" ,"key":"g5","label":"Gate 5","xlabel":"Go-Live Freigabe"},
    {"type":"phase","key":"p5","label":"Phase 5\nWartung & Support"},
    {"type":"end"  ,"key":"end","label":"Post-\nImplementation-\nCheck"},
]

def _done_v(key: str) -> bool:
    flags = {
        "start": st.session_state.get("phase0_complete", False),
        "g1":    st.session_state.get("gate1_complete", False),
        "p1":    st.session_state.get("phase1_complete", False),
        "g2":    st.session_state.get("gate2_complete", False),
        "p2":    st.session_state.get("phase2_complete", False),
        "g3":    st.session_state.get("gate3_complete", False),
        "p3":    st.session_state.get("phase3_complete", False),
        "g4":    st.session_state.get("gate4_complete", False),
        "p4":    st.session_state.get("phase4_complete", False),
        "g5":    st.session_state.get("gate5_complete", False),
        "p5":    st.session_state.get("phase5_complete", False),
        "end":   st.session_state.get("postimpl_complete", False) or st.session_state.get("all_complete", False),
    }
    return bool(flags.get(key, False))


_order = [s["key"] for s in _STEPS_V]
def _current_idx_v() -> int:
    for i, k in enumerate(_order):
        if k == "start":
            continue
        if not _done_v(k):
            return max(0, i-1)
    return len(_order) - 1


main, aside = st.columns([7, 3], gap="small")  

with aside:
    st.markdown('<div style="position:sticky; top:1rem;">', unsafe_allow_html=True)
    st.subheader("Prozess-Status")

    idx = _current_idx_v()

    if GV:
        g = Digraph("sg_overview_vertical_compact")
        g.attr(rankdir="TB", splines="polyline")
        # schmal + hoch; vor dem Zeichnen setzen
        g.attr("graph", margin="0.02", size="0.80,2.0", dpi="60")
        g.attr("node",  fontname="Inter, Helvetica, Arial", fontsize="12")
        g.attr("edge",  arrowsize="0.6")

        # Farben: fertig = grün, aktuell = grau, offen = weiß
        COLOR_DONE_NODE, COLOR_DONE_BORDER = "#2ECC71", "#1E8449"
        COLOR_CURRENT,   COLOR_BORDER_CUR  = "#ECEFF1", "#9E9E9E"
        COLOR_PENDING = "white"
        EDGE_DONE, EDGE_CURRENT, EDGE_PENDING = "#1E8449", "#9E9E9E", "#CFD8DC"

        for i, s in enumerate(_STEPS_V):
            is_current = (i == idx)
            is_done    = _done_v(s["key"])

            if is_done:
                fill, border = COLOR_DONE_NODE, COLOR_DONE_BORDER
            elif is_current:
                fill, border = COLOR_CURRENT, COLOR_BORDER_CUR
            else:
                fill, border = COLOR_PENDING, "#2C3E50"

            node_kwargs = {"style": "filled", "fillcolor": fill, "color": border}
            if s.get("xlabel"):
                node_kwargs["xlabel"] = s["xlabel"]

            # noch schmalere Nodes
            if s["type"] in ("start","end"):
                g.node(s["key"], s["label"], shape="circle",  width="0.60", height="0.60", **node_kwargs)
            elif s["type"] == "gate":
                g.node(s["key"], s["label"], shape="diamond", width="0.70", height="0.50", **node_kwargs)
            else:  # phase
                g.node(s["key"], s["label"], shape="box",     width="1.00", height="0.40", **node_kwargs)

            if i < len(_STEPS_V)-1:
                if is_done:          edge_color, pen = EDGE_DONE, "2"
                elif is_current:     edge_color, pen = EDGE_CURRENT, "2"
                else:                edge_color, pen = EDGE_PENDING, "1"
                g.edge(s["key"], _STEPS_V[i+1]["key"], color=edge_color, penwidth=pen)

        # WICHTIG: als DOT-Source rendern → Streamlit skaliert sauber
        st.graphviz_chart(g.source, use_container_width=True)


        # --- SVG rendern & an Spaltenbreite anpassen ---
        st.graphviz_chart(g, use_container_width=True)

    else:
        # Fallback ohne Graphviz – kompakt
        for i, s in enumerate(_STEPS_V):
            icon = "✅" if _done_v(s["key"]) else ("⚪️" if i == idx else "🕗")
            label_clean = " ".join(s["label"].splitlines())
            color = "#2ECC71" if _done_v(s["key"]) else ("#6b7280" if i == idx else "#111827")
            st.markdown(f"<div style='color:{color}; font-size:14px'>{icon} {label_clean}</div>", unsafe_allow_html=True)
            if s.get("xlabel"):
                st.markdown(f"<div style='color:#6b7280; font-size:12px'>{s['xlabel']}</div>", unsafe_allow_html=True)
            if i < len(_STEPS_V)-1:
                st.divider()


with main:
    # -------------------------------------------------------------------
    # PHASE 0: Potenzieller Prozess
    # -------------------------------------------------------------------
    with st.expander("Phase 0: Potenzieller Prozess", expanded=True):
        st.subheader("Angaben zum Prozess")
        prozessname = st.text_input("Wie heißt der Prozess?", key="prozessname")
        eigentuemer = st.text_input("Wer ist Prozesseigentümer?", key="prozesseigentuemer")


        if st.button("✅ Phase 0 abschließen"):
            if prozessname.strip() and eigentuemer.strip():
                st.session_state.phase0_complete = True
                st.success("✅ Phase 0 abgeschlossen – weiter zu Gate 1.")
                st.rerun() 
            else:
                st.warning("Bitte beide Felder ausfüllen.")

    # -------------------------------------------------------------------
    # GATE 1: RPA-Eignungstest
    # -------------------------------------------------------------------
    if st.session_state.phase0_complete:
        with st.expander("Gate 1: RPA-Eignungstest", expanded=True):
            st.subheader("RPA-Eignungstest")

            g1_fragen = {
                "regelbasiert": "Ist der Prozess regelbasiert?",
                "änderung": "Wird sich der Prozess oder die verwendeten IT-Systeme in naher Zukunft ändern?",
                "strukturiert": "Sind die verwendeten Dokumente im Prozess strukturiert aufgebaut?",
                "häufig_mehrere": "Wird der Prozess häufig durchgeführt oder wird er von mehr als einer Person bearbeitet?",
                "digital": "Sind die Ein- und Ausgaben des Prozesses digital?",
                "regelmäßig": "Wird der Prozess regelmäßig durchgeführt?",
                "wenig_ausnahmen": "Hat der Prozess wenige Ausnahmen?",
                "mehrere_systeme": "Werden mehrere Systeme für die Bearbeitung des Prozesses verwendet?",
                "fehleranfällig": "Ist der Prozess anfällig für menschliche Fehler?",
                "beschreibung": "Gibt es eine detaillierte Beschreibung über die Interaktion mit den IT-Systemen, Dateien und Schnittstellen?"
            }

            antworten_g1 = {}
            for key, frage in g1_fragen.items():
                antworten_g1[key] = st.radio(frage, ["Ja", "Nein"], horizontal=True, key=f"g1_{key}")

            if st.button("✅ Gate 1 prüfen"):
                if all(val == "Ja" for val in antworten_g1.values()):
                    st.success("✅ Gate 1 bestanden. Prozess geeignet – weiter zu Phase 1.")
                    st.session_state.gate1_complete = True
                    st.rerun() 
                else:
                    st.error("❌ Prozess ist für RPA **nicht geeignet** – mindestens eine Bedingung ist nicht erfüllt.")
                    st.session_state.gate1_complete = False
                    st.stop()

    # -------------------------------------------------------------------
    # PHASE 1: Prozessanalyse / -vorbereitung
    # -------------------------------------------------------------------
    if st.session_state.get("gate1_complete"):
        with st.expander("Phase 1: Prozessanalyse/-vorbereitung", expanded=True):
            st.subheader("Organisatorische & technische Vorbereitung")

            q_mgmt      = st.radio("Unterstützt das Management die Automatisierung?", ["Ja", "Nein"], horizontal=True)
            q_it        = st.radio("Ist der Prozess technisch umsetzbar (IT-Infrastruktur)?", ["Ja", "Nein"], horizontal=True)
            q_capacity  = st.radio("Sind Kapazitäten für Wartung & Betrieb vorhanden?", ["Ja", "Nein"], horizontal=True)

            betreiber   = st.text_input("Wer ist für den **Betrieb** des RPA-Bots zuständig? (E-Mail)")
            wartung     = st.text_input("Wer ist für die **Wartung** des RPA-Bots zuständig? (E-Mail)")

            q_endusers  = st.radio("Sind alle End-Benutzenden des Prozesses berücksichtigt worden?", ["Ja", "Nein"], horizontal=True)
            systeme     = st.text_input("Welche existierenden IT-Systeme sind involviert?")

            q_doc_full  = st.radio("Wurde der Prozess ausführlich dokumentiert?", ["Ja", "Nein"], horizontal=True)
            q_time_log  = st.radio("Wurde ein Zeitprotokoll des Prozesses erstellt?", ["Ja", "Nein"], horizontal=True)
            q_doc_ok    = st.radio("Entspricht die Dokumentation den Anforderungen der Prozessverantwortlichen?", ["Ja", "Nein"], horizontal=True)

            if st.button("✅ Phase 1 prüfen & abschließen"):
                radios_ok = all(ans == "Ja" for ans in [
                    q_mgmt, q_it, q_capacity, q_endusers, q_doc_full, q_time_log, q_doc_ok
                ])
                betreiber_ok = bool(EMAIL_RE.match((betreiber or "").strip()))
                wartung_ok   = bool(EMAIL_RE.match((wartung or "").strip()))
                systeme_ok   = bool((systeme or "").strip())

                if radios_ok and betreiber_ok and wartung_ok and systeme_ok:
                    st.success("✅ Phase 1 abgeschlossen – weiter zu Gate 2.")
                    st.session_state.phase1_complete = True
                    st.rerun() 
                else:
                    if not radios_ok:
                        st.error("Alle Ja/Nein-Fragen müssen mit **Ja** beantwortet sein.")
                    if not betreiber_ok:
                        st.error("Bitte eine **gültige E-Mail** für den Betrieb angeben.")
                    if not wartung_ok:
                        st.error("Bitte eine **gültige E-Mail** für die Wartung angeben.")
                    if not systeme_ok:
                        st.error("Bitte die **involvierten IT-Systeme** angeben.")

    # -------------------------------------------------------------------
    # GATE 2: RPA-Score
    # -------------------------------------------------------------------

    if st.session_state.get("gate1_complete"):   # Gate 1 muss erledigt sein
        with st.expander("Gate 2: RPA-Score", expanded=True):
            st.subheader("RPA-Score berechnen")

            ternary = {"Ja": 1.0, "Nein": 0.0, "Unbekannt": 0.5}

            with st.form("gate2_form"):
                # 10 binäre/ternäre Kriterien
                q = {}
                q["apps_zugang"]      = st.radio("Sind alle Anwendungen / Software zugänglich?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["schon_autom"]      = st.radio("Ist der Prozess bereits in einer anderen Form automatisiert?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["komplex"]          = st.radio("Ist der Prozess komplex?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["nur_digital"]      = st.radio("Werden nur digitale Daten verwendet?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["aenderung"]        = st.radio("Wird sich der Prozess in näherer Zukunft ändern?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["stabil_stabile_sw"]= st.radio("Ist der Prozess stabil und verwendet stabile Anwendungen?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["standardisiert"]   = st.radio("Ist der Prozess standardisiert?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["strukturierte"]    = st.radio("Verwendet der Prozess strukturierte Daten?", ["Ja","Nein","Unbekannt"], horizontal=True)
                q["begrenzte_ausn"]   = st.radio("Hat der Prozess begrenzte Ausnahmen/Alternativen?", ["Ja","Nein","Unbekannt"], horizontal=True)
                richtlinien           = st.radio("Sind die Richtlinien des Prozesses eindeutig und klar dokumentiert?", ["Ja","Nein","Unbekannt"], horizontal=True)

                st.markdown("### Gesamtzeit des Prozesses (pro Woche)")
                dauer_min = st.number_input("Wie lange dauert der Prozess (eine Ausführung)? (Minuten)", min_value=0, step=1, value=0)
                freq_w   = st.number_input("Wie häufig kommt der Prozess pro Woche vor? (Anzahl)", min_value=0, step=1, value=0)

                st.markdown("### Nutzen des Prozesses (Mehrfachauswahl möglich)")
                alle_benefits = [
                    "Reduzierte Prozesszeiten",
                    "Entlastung der Routinearbeiten",
                    "Geringere Fehlerquote",
                    "Erhöhte Kundenzufriedenheit und -service",
                    "24 / 7 Betrieb",
                    "Verbesserung der Mitarbeitenden-Skills",
                    "Standardisierung",
                ]
                selected_benefits = st.multiselect("Welchen Nutzen wird die Automatisierung haben?", alle_benefits, default=[])

                submit = st.form_submit_button("RPA-Score berechnen")

            if submit:
                # --- 1) Binär/Ternär (10 + 1 für Richtlinien) ---
                bin_sum = sum(ternary[v] for v in q.values()) + ternary[richtlinien]  # 11 Faktoren

                # --- 2) Gesamtzeit T = Dauer * Häufigkeit; auf 0..1 mappen gemäß Tabelle ---
                T = float(dauer_min) * float(freq_w)  # Minuten/Woche
                if T < 30:
                    t_score = 0.0
                elif T < 60:
                    t_score = 0.25
                elif T < 180:
                    t_score = 0.5
                else:
                    t_score = 1.0

                # --- 3) Nutzen linear gestaffelt: Anteil der ausgewählten Vorteile von 7 ---
                benefit_score = (len(selected_benefits) / 7.0)

                # --- 4) Gesamtscore x = (11 Binär/Ternär) + (T) + (Nutzen) = 13 Kriterien
                x = bin_sum + t_score + benefit_score

                # --- 5) Normalisieren auf 0..100 gemäß N = (x * 100) / 12
                # In der Arbeit sind Dauer & Häufigkeit zusammengefasst; daher 12 statt 13.
                N = round((x * 100.0) / 12.0, 2)

                # --- 6) Einordnung ---
                if N < 50:
                    level = "🔴 Ungeeignet (<50)"
                elif N < 70:
                    level = "🟡 Geeignet (50–69)"
                else:
                    level = "🟢 Sehr gut geeignet (≥70)"

                st.metric("RPA-Score", f"{N:.2f} / 100")
                st.write(f"**Einstufung:** {level}")

                with st.expander("Berechnungsdetails"):
                    st.write({
                        "Minuten pro Woche (T)": T,
                        "T-Score (0–1)": t_score,
                        "Ausgewählte Benefits": len(selected_benefits),
                        "Benefit-Score (0–1)": benefit_score,
                        "Binär/Ternär Summe (0–11)": bin_sum,
                        "x (ungewichtet)": x,
                        "N (normalisiert 0–100)": N,
                    })

                # --- 7) Gate-Fortschritt setzen ---
                if N >= 50:
                    st.session_state["gate2_complete"] = True
                    st.success("Gate 2 abgeschlossen – weiter zur **Phase 2**.")
                else:
                    st.session_state["gate2_complete"] = False
                    st.error("Score < 50 → Prozess aktuell **nicht** geeignet. Bitte optimieren/prüfen.")

    # -------------------------------------------------------------------
    # PHASE 2: Design- / Entwicklungsphase (sichtbar NACH Gate 2)
    # -------------------------------------------------------------------
    if st.session_state.get("gate2_complete"):
        with st.expander("Phase 2: Design- / Entwicklungsphase", expanded=True):
            st.subheader("Planung der Entwicklung")

            entwickler = st.text_input("Wer übernimmt die Entwicklung des Bots? (Name/Team)")
            req_clarified = st.radio(
                "Wurde der Prozess überprüft und die Anforderungen mit dem Prozess-Owner abgeklärt?",
                ["Ja", "Nein"], horizontal=True
            )
            reuse_possible = st.radio(
                "Gibt es die Möglichkeit, vorhandene Codes aus bestehenden Bots wiederzuverwenden?",
                ["Ja", "Nein"], horizontal=True
            )

            if st.button("✅ Phase 2 prüfen & abschließen"):
                dev_ok = bool((entwickler or "").strip())
                radios_ok = (req_clarified == "Ja" and reuse_possible == "Ja")

                if dev_ok and radios_ok:
                    st.success("✅ Phase 2 abgeschlossen – weiter zu Gate 3.")
                    st.session_state.phase2_complete = True
                    st.rerun() 
                else:
                    if not dev_ok:
                        st.error("Bitte eine verantwortliche Person / ein Team für die Entwicklung eintragen.")
                    if not radios_ok:
                        st.error("Beide Fragen müssen mit **Ja** beantwortet werden.")


    # -------------------------------------------------------------------
    # GATE 3: Prototyp-Freigabe (sichtbar NACH Phase 2)
    # -------------------------------------------------------------------
    if st.session_state.get("phase2_complete"):
        with st.expander("Gate 3: Prototyp-Freigabe", expanded=True):
            st.subheader("Qualitäts- & Sicherheitskriterien für den Prototyp")

            # Positiv zu beantwortende Kriterien (müssen "Ja" sein)
            g3_pos_questions = {
                "modular": "Wurde der RPA-Bot modular aufgebaut?",
                "friendly_errors": "Wurden verständliche Fehlermeldungen eingebaut?",
                "manual_fallback": "Können Benutzende im Falle eines Ausfalles den Prozess manuell abschließen?",
                "notify_users": "Gibt es eine Meldung an den Benutzenden bei Erfolg oder Fehlleistung des Bots?",
                "error_msg": "Wird bei einem Fehler eine Fehlermeldung ausgegeben?",
                "privacy": "Ist der RPA-Bot datenschutzkonform und manipulationssicher?",
                "consistent_output": "Liefert der Bot stets die gleichen Ausgaben?",
                "access_control": "Wurde sichergestellt, dass nur Nutzende des Prozesses Zugriff auf ausgegebene Daten erhalten?",
                "works_as_intended": "Arbeitet der RPA-Bot wie vorgesehen?",
                "doc_complete": "Wurde der RPA-Bot ausführlich dokumentiert?",
            }

            # Negativ formuliertes Kriterium (muss "Nein" sein)
            g3_neg_key = "causes_sys_errors"
            g3_neg_label = "Verursacht der Bot ein Systemfehler in den IT-Systemen in denen er arbeitet?"

            answers_pos = {}
            for k, label in g3_pos_questions.items():
                answers_pos[k] = st.radio(label, ["Ja", "Nein"], horizontal=True, key=f"g3_{k}")

            ans_neg = st.radio(g3_neg_label, ["Ja", "Nein"], horizontal=True, key=f"g3_{g3_neg_key}")

            if st.button("✅ Gate 3 prüfen"):
                pos_ok = all(v == "Ja" for v in answers_pos.values())
                neg_ok = (ans_neg == "Nein")

                if pos_ok and neg_ok:
                    st.success("✅ Gate 3 bestanden – weiter zur Testphase (Gate 4).")
                    st.session_state.gate3_complete = True
                    st.rerun() 
                else:
                    if not pos_ok:
                        st.error("Alle positiv formulierten Kriterien müssen mit **Ja** erfüllt sein.")
                    if not neg_ok:
                        st.error("Der Bot darf **keine** Systemfehler verursachen (Antwort hier muss **Nein** sein).")
                    st.stop()
    
    # -------------------------------------------------------------------
    # --- PHASE 3: Testphase ---
    # -------------------------------------------------------------------
    if st.session_state.get("gate3_complete"):   # erst nach Gate 3 sichtbar
        with st.expander("Phase 3: Testphase", expanded=True):
            st.subheader("Testphase")

            t1 = st.radio("Ist eine Testumgebung eingerichtet?", ["Ja", "Nein"], horizontal=True, key="p3_testumgebung")
            t2 = st.radio("Besteht ein Testplan für den Bot?",   ["Ja", "Nein"], horizontal=True, key="p3_testplan")

            # Abschluss-Button
            if st.button("✅ Phase 3 abschließen", key="btn_phase3_done",
                        disabled=st.session_state.get("phase3_complete", False)):
                if t1 == "Ja" and t2 == "Ja":
                    st.session_state["phase3_complete"] = True   # ← oder 'phase4_complete', wenn du sie als Phase 4 führst
                    st.success("Phase 3 abgeschlossen – weiter zu Gate 4.")
                    st.rerun()
                else:
                    st.error("Bitte beide Fragen mit **Ja** beantworten, um die Testphase abzuschließen.")


    # -------------------------------------------------------------------
    # GATE 4: Produktionsfreigabe (sichtbar NACH Phase 3)
    # -------------------------------------------------------------------
    if st.session_state.get("phase3_complete"):
        with st.expander("Gate 4: Produktionsfreigabe", expanded=True):
            st.subheader("Tests & Freigabe durch User")

            g4_questions = {
                "komponententest": "Wurde ein Komponententest (=jedes Modul einzeln testen) durchgeführt?",
                "integrationstest": "Wurde ein Integrationstest (=Interaktionen mit Systemen überprüfen) durchgeführt?",
                "funktionstest": "Wurde ein Funktionstest (= Test aus Nutzersicht) durchgeführt?",
                "kriterien_user": "Wurden die Kriterien für die Freigabe mit den Usern festgelegt?",
                "demo_user": "Wurde der Bot für die End-User demonstriert?",
                "schriftliche_freigabe": "Wurde eine schriftliche Freigabe von den Usern erteilt?",
            }

            g4_answers = {}
            for key, frage in g4_questions.items():
                g4_answers[key] = st.radio(frage, ["Ja", "Nein"], horizontal=True, key=f"g4_{key}")

            if st.button("✅ Gate 4 prüfen"):
                if all(ans == "Ja" for ans in g4_answers.values()):
                    st.success("✅ Gate 4 bestanden – der Bot ist produktionsreif. Weiter zu Phase 4.")
                    st.session_state.gate4_complete = True
                    st.rerun() 
                else:
                    st.error("Alle Kriterien müssen mit **Ja** beantwortet sein, damit Gate 4 bestanden wird.")
                    st.stop()

    # -------------------------------------------------------------------
    # PHASE 4: Implementierungsphase (sichtbar NACH Gate 4)
    # -------------------------------------------------------------------
    if st.session_state.get("gate4_complete"):
        with st.expander("Phase 4: Implementierungsphase", expanded=True):
            st.subheader("Go-Live & Einführung")

            g5_questions = {
                "plan": "Gibt es einen Implementierungsplan?",
                "transport": "Ist der Bot erfolgreich transportiert?",
                "golive_comm": "Wurde der „Go Live“ des Bots kommuniziert?",
                "benefits_comm": "Sind die Vorteile des Bots kommuniziert worden?",
                "training": "Wurde eine Schulung für die Benutzenden angeboten?",
                "manuals": "Werden Benutzerhandbücher für die Benutzenden bereitgestellt?",
                "strategy": "Wurde eine Strategie entwickelt, um die kontinuierliche Wartung und Verbesserung des RPA-Bots sicherzustellen?",
            }

            g5_answers = {}
            for key, frage in g5_questions.items():
                g5_answers[key] = st.radio(frage, ["Ja", "Nein"], horizontal=True, key=f"p4_{key}")

            if st.button("✅ Phase 4 prüfen & abschließen"):
                if all(ans == "Ja" for ans in g5_answers.values()):
                    st.success("✅ Phase 4 abgeschlossen – bereit für Gate 5.")
                    st.session_state.phase4_complete = True
                    st.rerun() 
                else:
                    st.error("Alle Kriterien müssen mit **Ja** beantwortet sein, um Phase 4 abzuschließen.")

    # -------------------------------------------------------------------
    # GATE 5: Go-Live-Freigabe (sichtbar NACH Phase 4)
    # -------------------------------------------------------------------
    if st.session_state.get("phase4_complete"):
        with st.expander("Gate 5: Go-Live-Freigabe", expanded=True):
            st.subheader("Freigabeentscheidung durch Endnutzende")

            ok_for_users = st.radio(
                "Funktioniert der Bot nach den Erwartungen der Endnutzenden?",
                ["Ja", "Nein"], horizontal=True, key="g5_ok"
            )

            if st.button("✅ Gate 5 prüfen"):
                if ok_for_users == "Ja":
                    st.success("✅ Gate 5 bestanden – Go-Live freigegeben.")
                    st.session_state.gate5_complete = True
                    st.rerun() 
                    # Optional: Gesamtabschluss markieren
                    st.session_state.all_complete = True
                else:
                    st.session_state.gate5_complete = False
                    st.warning("🔄 Go-Live **nicht** freigegeben – bitte zur **Entwicklungsphase** zurückkehren und nachbessern.")
                    st.session_state.phase2_complete = False
                    st.session_state.gate3_complete = False
                    st.session_state.phase3_complete = False
                    st.session_state.gate4_complete = False
                    st.stop()
                
    # -------------------------------------------------------------------
    # PHASE 5: Wartung & Support (sichtbar NACH Gate 5)
    # -------------------------------------------------------------------
    if st.session_state.get("gate5_complete"):
        with st.expander("Phase 5: Wartung & Support", expanded=True):
            st.subheader("Betrieb, Monitoring & kontinuierliche Verbesserung")

            p5_questions = {
                "daily_monitor": "Wird der RPA-Bot täglich überwacht?",
                "contin_improve": "Wird der RPA-Bot kontinuierlich verbessert?",
                "adapt_updates": "Wird der RPA-Bot an IT-System-Änderungen/Updates angepasst?",
                "log_error_rate": "Wird die Fehlerrate des Bots dokumentiert?",
                "dashboard": "Können Benutzende den Bot über ein Dashboard überwachen?",
                "suggestions": "Können Benutzende Verbesserungsvorschläge abgeben?",
                "sla_outage": "Gibt es eine Vereinbarung mit den Usern im Falle eines Ausfalles?",
            }

            p5_answers = {}
            for key, frage in p5_questions.items():
                p5_answers[key] = st.radio(frage, ["Ja", "Nein"], horizontal=True, key=f"p5_{key}")

            if st.button("✅ Phase 5 prüfen & abschließen"):
                if all(ans == "Ja" for ans in p5_answers.values()):
                    st.success("✅ Phase 5 abgeschlossen – Betrieb geregelt.")
                    st.session_state.phase5_complete = True
                    st.rerun() 
                else:
                    st.error("Alle Kriterien müssen mit **Ja** beantwortet sein, um Phase 5 abzuschließen.")

    # -------------------------------------------------------------------
    # POST-IMPLEMENTATION-CHECK (sichtbar NACH Phase 5)
    # -------------------------------------------------------------------
    if st.session_state.get("phase5_complete"):
        with st.expander("Post-Implementation-Check", expanded=True):
            st.subheader("KPI-Messung im Betrieb")

            kpi_measured = st.radio(
                "Werden KPIs gemessen?", ["Ja", "Nein"],
                horizontal=True, key="pic_measured"
            )

            # Wenn auf "Nein" gestellt wird: Diagramm ausblenden
            if kpi_measured != "Ja":
                st.session_state["pic_show_chart"] = False

            if kpi_measured == "Ja":
                # --- Formular: kein Re-Run bei jedem Tippen ---
                with st.form("pic_form", clear_on_submit=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        kpi_error_rate = st.number_input(
                            "Fehlerrate (%)", min_value=0.0, max_value=100.0, step=0.1,
                            key="pic_err_rate"
                        )
                        kpi_exec_time_min = st.number_input(
                            "Durchschnittliche Ausführungszeit (Minuten)",
                            min_value=0.0, step=0.1, key="pic_exec_min"
                        )
                    with col2:
                        kpi_fix_time_min = st.number_input(
                            "Durchschnittliche Zeit zur Fehlerbehebung (Minuten)",
                            min_value=0.0, step=0.1, key="pic_fix_min"
                        )
                        kpi_manual_savings_min = st.number_input(
                            "Einsparung manueller Aufwand (Minuten/Woche)",
                            min_value=0.0, step=1.0, key="pic_save_min"
                        )

                    st.markdown("### Kosten- / Nutzen-Analyse")
                    runs_per_week = st.number_input(
                        "Anzahl Bot-Ausführungen pro Woche",
                        min_value=0, step=1, value=50, key="pic_runs_week"
                    )
                    hourly_cost = st.number_input(
                        "Kostensatz pro Stunde (€)",
                        min_value=0.0, step=1.0, value=20.0, key="pic_hourly_cost"
                    )

                    submit_pic = st.form_submit_button("Diagramm aktualisieren")

                # Flag setzen, damit die Auswertung auch nach dem Submit sichtbar bleibt
                if submit_pic:
                    st.session_state["pic_show_chart"] = True

                # --- Auswertung & Diagramm nur zeigen, wenn Flag aktiv ---
                if st.session_state.get("pic_show_chart", False):
                    # Aus dem Session State lesen (stabil über Re-Runs)
                    err_rate   = float(st.session_state.get("pic_err_rate", 0.0))
                    mttr_min   = float(st.session_state.get("pic_fix_min", 0.0))
                    save_min_w = float(st.session_state.get("pic_save_min", 0.0))
                    runs_w     = int(st.session_state.get("pic_runs_week", 0))
                    rate_eur_h = float(st.session_state.get("pic_hourly_cost", 20.0))

                    error_events_per_week = runs_w * (err_rate / 100.0)
                    error_minutes_week    = error_events_per_week * mttr_min
                    error_cost_week       = (error_minutes_week / 60.0) * rate_eur_h

                    saving_cost_week      = (save_min_w / 60.0) * rate_eur_h
                    net_benefit_week      = saving_cost_week - error_cost_week
                    net_benefit_year      = net_benefit_week * 52

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Kosten Fehlerbehebung / Woche", f"{error_cost_week:,.2f} €")
                    c2.metric("Wert Zeitersparnis / Woche",    f"{saving_cost_week:,.2f} €")
                    c3.metric("Netto-Nutzen / Woche",          f"{net_benefit_week:,.2f} €")
                    st.caption(f"≈ **{net_benefit_year:,.2f} €** Netto-Nutzen pro Jahr (52 Wochen).")

                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots(figsize=(5.2, 3.2))
                    labels = ["Fehlerkosten", "Zeitersparnis", "Netto"]
                    values = [error_cost_week, saving_cost_week, net_benefit_week]
                    ax.bar(labels, values)
                    ax.set_ylabel("€ pro Woche")
                    ax.set_title("Kosten / Nutzen")
                    for i, v in enumerate(values):
                        ax.text(i, v, f"{v:,.0f} €", ha="center", va="bottom", fontsize=9)
                    st.pyplot(fig, clear_figure=True)

                    # optional für Export
                    st.session_state["pic_cost_benefit"] = {
                        "error_cost_week": error_cost_week,
                        "saving_cost_week": saving_cost_week,
                        "net_benefit_week": net_benefit_week,
                        "net_benefit_year": net_benefit_year,
                        "runs_per_week": runs_w,
                        "hourly_cost": rate_eur_h,
                    }

            else:
                st.info("Bitte eine KPI-Messung etablieren (Monitoring, Protokollierung, Dashboard), "
                        "um den Post-Implementation-Check abzuschließen.")

            # Abschluss-Button außerhalb der Form (damit das Formular erhalten bleibt)
            if st.button("✅ Post-Implementation-Check abschließen", key="btn_pic_done"):
                if kpi_measured == "Ja":
                    filled = all(v is not None for v in [
                        st.session_state.get("pic_err_rate"),
                        st.session_state.get("pic_exec_min"),
                        st.session_state.get("pic_fix_min"),
                        st.session_state.get("pic_save_min"),
                    ])
                    plausible = (
                        0.0 <= st.session_state.get("pic_err_rate", 0.0) <= 100.0 and
                        st.session_state.get("pic_exec_min", 0.0) >= 0.0 and
                        st.session_state.get("pic_fix_min", 0.0) >= 0.0 and
                        st.session_state.get("pic_save_min", 0.0) >= 0.0
                    )
                    if filled and plausible:  # <— hier lag der Fehler
                        st.session_state["postimpl_complete"] = True
                        st.session_state["all_complete"] = True
                        st.success("✅ Post-Implementation-Check abgeschlossen.")
                        st.rerun()
                    else:
                        st.error("Bitte alle KPI-Felder sinnvoll befüllen.")
                else:
                    st.error("Post-Implementation-Check kann erst abgeschlossen werden, wenn KPIs gemessen werden (Antwort „Ja“).")

