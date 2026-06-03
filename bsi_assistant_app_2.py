# bsi_assistant_app.py
# FINAL VERSION — Phase 1–5
# Phase 1–3: LLM + File Search (BSI reading)
# Phase 4: Architecture-based threat aggregation (deterministic)
# Phase 5: Expert customization (data_editor)

import os
import sys
import time
import re
import yaml
import json
import uuid
import streamlit as st
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# Make the app importable/runnable regardless of the current working directory
# (e.g. when deployed from a subfolder on Streamlit Cloud, where CWD is the repo
# root rather than this file's folder). This puts `engine` and the data files on
# a known base path.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine.logic import (
    split_components,
    map_to_ind,
    map_component,
    expand_modules,
    check_completeness,
    looks_like_query,
    is_component_like,
    general_module_question,
)

# set_page_config MUST be the first Streamlit command in the script.
st.set_page_config(
    page_title="BSI IT-Grundschutz Assistant",
    page_icon="🛡️",
    layout="wide",
)

# --- Design system / premium UI ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root{
        --ink:#241019; --brand:#7A003E; --brand-700:#5C002E; --accent:#C9A227;
        --slate:#3A2A30; --muted:#8A737C; --line:rgba(60,15,35,.12);
        --canvas:#FAFAFA; --surface:#FFFFFF;
    }

    /* ChatGPT / Claude–style type: Inter (closest free match to Söhne), crisp + slightly tight */
    html, body, .stApp, [class*="css"], [data-testid="stMarkdownContainer"]{
        font-family:'Inter','Söhne','Styrene B',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
        color:var(--slate); -webkit-font-smoothing:antialiased; letter-spacing:-.011em;
    }
    .stApp{ background:var(--canvas); }
    .block-container{ padding:.55rem 2.6rem 4rem; max-width:100%; }
    #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
    [data-testid="stStatusWidget"]{ visibility:hidden; }
    [data-testid="stHeader"]{ display:none; }   /* flush the content to the top */

    h1,h2,h3,h4{ color:var(--ink); font-weight:700; letter-spacing:-.02em; }
    .eyebrow{ text-transform:uppercase; letter-spacing:.22em; font-size:.68rem;
        font-weight:600; color:var(--brand); }
    .section-title{ font-size:1.3rem; font-weight:700; color:var(--ink); margin:.15rem 0 .1rem; }
    .section-sub{ color:var(--muted); font-size:.9rem; margin-bottom:1rem; }

    /* Header */
    .app-header{
        background:#F8E8EE;   /* uniform soft light red */
        border:1px solid var(--line); border-left:4px solid var(--brand);
        border-radius:12px; padding:.7rem 1.3rem; margin:0 0 1rem;
        box-shadow:0 3px 12px -10px rgba(60,15,35,.20);
    }
    .app-header .eyebrow{ color:var(--brand); font-size:.6rem; letter-spacing:.18em; }
    .app-header-title{ font-size:1.25rem; font-weight:800; color:var(--ink); letter-spacing:-.02em; line-height:1.15; margin-top:.15rem; }
    .app-header-sub{ color:var(--muted); font-size:.82rem; margin-top:.18rem; max-width:100ch; line-height:1.4; }

    /* Metric cards */
    .metric-card{ background:var(--surface); border:1px solid var(--line); border-radius:14px;
        padding:1rem 1.15rem; min-height:98px; display:flex; flex-direction:column;
        justify-content:center; gap:.35rem;
        box-shadow:0 2px 8px -4px rgba(60,15,35,.12); }
    .metric-label{ text-transform:uppercase; letter-spacing:.12em; font-size:.62rem; color:var(--muted);
        font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .metric-value{ font-size:1.9rem; font-weight:800; color:var(--ink); line-height:1; }
    .metric-card.accent{ background:var(--brand); border-color:var(--brand); }
    .metric-card.accent .metric-label{ color:#EAC9D5; }
    .metric-card.accent .metric-value{ color:#fff; }

    /* Buttons — force visible white label over the brand fill */
    .stButton>button, .stDownloadButton>button{
        border-radius:10px; border:1px solid var(--brand); background:var(--brand); color:#fff !important;
        font-weight:600; padding:.5rem 1.3rem; min-height:2.7rem;
        transition:background-color .2s ease, box-shadow .2s ease, transform .12s ease;
        box-shadow:0 4px 10px -6px rgba(122,0,62,.45);
    }
    .stButton>button *, .stDownloadButton>button *{ color:#fff !important; font-weight:600; }
    .stButton>button:hover, .stDownloadButton>button:hover{
        background:var(--brand-700); border-color:var(--brand-700);
        box-shadow:0 6px 14px -6px rgba(122,0,62,.5);
    }
    .stButton>button:active, .stDownloadButton>button:active{ transform:scale(.985); }

    /* Feedback link button — secondary (outline) style */
    [data-testid="stLinkButton"] a{
        border-radius:10px; border:1px solid var(--brand); background:transparent; color:var(--brand) !important;
        font-weight:600; min-height:2.7rem; transition:background-color .2s ease, color .2s ease;
    }
    [data-testid="stLinkButton"] a *{ color:var(--brand) !important; }
    [data-testid="stLinkButton"] a:hover{ background:var(--brand); color:#fff !important; }
    [data-testid="stLinkButton"] a:hover *{ color:#fff !important; }

    /* Tables, expanders */
    [data-testid="stDataFrame"], [data-testid="stTable"]{ border:1px solid var(--line); border-radius:12px; overflow:hidden; }
    [data-testid="stExpander"]{ border:1px solid var(--line); border-radius:12px; background:var(--surface); }
    /* Opaque bottom bar so scrolling content doesn't repaint through it (anti-flicker) */
    [data-testid="stBottom"]{ background:var(--canvas); box-shadow:none; }
    html, body{ overflow-x:hidden; }
    [data-testid="stExpander"] summary{ font-weight:600; color:var(--ink); }

    /* Sidebar */
    [data-testid="stSidebar"]{ background:var(--surface); border-right:1px solid var(--line); }
    /* Shift sidebar content (logo) to the very top */
    [data-testid="stSidebarHeader"]{ display:none !important; height:0 !important; padding:0 !important; }
    [data-testid="stSidebarUserContent"]{ padding-top:0.8rem !important; }
    [data-testid="stSidebarContent"]{ padding-top:0.8rem !important; }
    section[data-testid="stSidebar"] > div:first-child{ padding-top:0.8rem !important; }
    section[data-testid="stSidebar"] .block-container{ padding-top:0.8rem !important; }
    .side-brand{ font-weight:800; color:var(--ink); font-size:1.05rem; letter-spacing:-.01em; }
    .side-label{ text-transform:uppercase; letter-spacing:.16em; font-size:.64rem; color:var(--muted);
        font-weight:600; margin:1.1rem 0 .25rem; }

    /* Status + legend */
    .status-ok{ color:#1B7F4B; font-weight:600; font-size:.86rem; }
    .status-ok::before{ content:"●"; margin-right:.45rem; font-size:.65rem; vertical-align:middle; }
    .legend{ display:flex; gap:1.2rem; flex-wrap:wrap; margin:.1rem 0 .9rem; font-size:.82rem; color:var(--muted); }
    .legend span{ display:inline-flex; align-items:center; gap:.45rem; }
    .chip{ width:.72rem; height:.72rem; border-radius:4px; display:inline-block; }
    .chip-bsi{ background:#DCEDE2; border:1px solid #9FCBAE; }
    .chip-mod{ background:#FBEFD0; border:1px solid #E6C97A; }
    .chip-exp{ background:#DAE7F6; border:1px solid #9CBDE3; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------
# ENV + CLIENT
# --------------------------------------------------
load_dotenv()


def get_secret(name, default=None):
    """Resolve config from the environment / .env first (local dev), then from
    st.secrets (Streamlit Cloud). Env-first means a local run with a .env never
    touches st.secrets (avoiding the noisy 'No secrets files found' message); on
    Cloud the env is empty so it falls through to the dashboard secrets.
    """
    val = os.getenv(name)
    if val is not None:
        return val
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return default


OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else OpenAI()

ASSISTANT_ID = get_secret("OPENAI_ASSISTANT_ID")

SYNONYMS_FILE = os.path.join(_HERE, "data/synonyms_2022.yaml")
IND_MODULES_FILE = os.path.join(_HERE, "data/ind_modules_2022.yaml")
COMPOSITIONS_FILE = os.path.join(_HERE, "data/component_compositions.yaml")
THREAT_STORE_FILE = os.path.join(_HERE, "data/bsi_threat_store.json")
VDI_MAPPING_FILE = os.path.join(_HERE, "data/vdi2182_threat_mapping.yaml")
EXPERT_STORE_FILE = os.path.join(_HERE, "data/expert_threat_templates.json")

if not ASSISTANT_ID:
    st.error("OPENAI_ASSISTANT_ID not found in .env")
    st.stop()

# --------------------------------------------------
# LOADERS
# --------------------------------------------------
def load_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------
synonyms = load_yaml(SYNONYMS_FILE).get("canonical", {})
ind_modules = load_yaml(IND_MODULES_FILE).get("ind_modules", [])
_compositions_yaml = load_yaml(COMPOSITIONS_FILE)
compositions = _compositions_yaml.get("compositions", {})
inheritance = _compositions_yaml.get("inheritance", {})
threat_store = load_json(THREAT_STORE_FILE, {"modules": {}})
expert_store = load_json(EXPERT_STORE_FILE, {})
vdi_mapping = load_yaml(VDI_MAPPING_FILE).get("mappings", {})

title_lookup = {t.lower(): t for t in synonyms.keys()}

# ----------------------------
# ASSISTANT HELPERS (Phase 1–3)
# ----------------------------
TERMINAL = {"completed", "failed", "cancelled", "expired", "requires_action"}
_CITATION_MARKER = re.compile(r"【[^】]*】")
_FILE_NAME_CACHE = {}


def _filename(file_id):
    """Resolve a file_id -> original filename (cached)."""
    if file_id not in _FILE_NAME_CACHE:
        try:
            _FILE_NAME_CACHE[file_id] = client.files.retrieve(file_id).filename
        except Exception:
            _FILE_NAME_CACHE[file_id] = file_id
    return _FILE_NAME_CACHE[file_id]


def ask_assistant(prompt):
    """One-shot assistant call. Returns (text, [source_snippets])."""
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)
    while run.status not in TERMINAL:
        time.sleep(0.8)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
    if run.status != "completed":
        return f"_(assistant run ended: {run.status})_", []

    msgs = client.beta.threads.messages.list(thread_id=thread.id)
    latest = next((m for m in msgs.data if m.role == "assistant"), None)
    text_parts, file_ids = [], []
    if latest:
        for item in latest.content:
            if item.type == "text":
                text_parts.append(item.text.value)
                for ann in getattr(item.text, "annotations", []) or []:
                    if ann.type == "file_citation":
                        fc = getattr(ann, "file_citation", None)
                        fid = getattr(fc, "file_id", None) if fc else None
                        if fid:
                            file_ids.append(fid)

    # v2 file_search exposes only file_id (no quoted text) and injects 【…】
    # markers inline — strip the markers, surface the source filename(s).
    clean = _CITATION_MARKER.sub("", "\n".join(text_parts)).strip()
    sources = []
    for fid in dict.fromkeys(file_ids):
        name = _filename(fid)
        if name not in sources:
            sources.append(name)
    return clean, sources


def stream_assistant(prompt, placeholder, prefix=""):
    """Render the assistant reply all-at-once (token streaming reverted per
    user request). Same content as before — only the display differs.
    Returns (clean_text, sources)."""
    placeholder.markdown(prefix + "_Processing…_")
    text, sources = ask_assistant(prompt)
    placeholder.markdown(prefix + (text or "No response from assistant."))
    return text, sources


def code_for_component(comp_title):
    return next((m.get("code") for m in ind_modules if m.get("title") == comp_title), None)


def titles_for_component(comp_title):
    """Threat titles for a canonical component, incl. inherited IND.2.1."""
    code = code_for_component(comp_title)
    if not code:
        return []
    titles = []
    for mod in expand_modules([code], inheritance):
        for t in threat_store.get("modules", {}).get(mod, {}).get("threats", []):
            if t["title"] not in titles:
                titles.append(t["title"])
    return titles


# ----------------------------
# THREAT AGGREGATION
# ----------------------------
def aggregate_threats(arch_id):
    aggregated = {}

    base_modules = compositions[arch_id]["bsi_modules"]
    all_modules = expand_modules(base_modules, inheritance)
    inherited = [m for m in all_modules if m not in base_modules]

    # ---- BSI threats (incl. inherited ICS-component threats, e.g. IND.2.1)
    for mod in all_modules:
        mod_data = threat_store["modules"].get(mod)
        if not mod_data:
            continue

        label = f"{mod} (inherited)" if mod in inherited else mod
        for t in mod_data["threats"]:
            title = t["title"]
            row_id = f"BSI::{title}"

            if row_id not in aggregated:
                aggregated[row_id] = {
                    "_row_id": row_id,
                    "Threat": title,
                    "Source Modules": [label],
                    "C": False,
                    "I": False,
                    "A": False,
                    "S": False,
                    "Origin": "BSI",
                    "Comments": "",
                    "Modified": False
                }
            else:
                aggregated[row_id]["Source Modules"].append(label)

    # ---- Apply VDI mapping
    for row in aggregated.values():
        impacts = vdi_mapping.get(row["Threat"], {}).get("impacts", [])
        for k in impacts:
            row[k] = True

    # ---- Expert templates
    for t in expert_store.get(arch_id, []):
        row_id = f"EXPERT::{t['Threat']}"
        aggregated[row_id] = {
            "_row_id": row_id,
            "Threat": t["Threat"],
            "Source Modules": [],
            "C": "C" in t["CIA_S"],
            "I": "I" in t["CIA_S"],
            "A": "A" in t["CIA_S"],
            "S": "S" in t["CIA_S"],
            "Origin": "Expert",
            "Comments": t.get("Comments", ""),
            "Modified": True
        }

    return pd.DataFrame(aggregated.values())


def _row_style(row):
    """Color matrix rows by provenance: BSI (green) / Modified (amber) / Expert (blue)."""
    if row.get("Origin") == "Expert":
        bg = "background-color: #EAF1FA"
    elif row.get("Modified", False):
        bg = "background-color: #FBF3DC"
    else:
        bg = "background-color: #F1F8F3"
    return [bg] * len(row)

# --------------------------------------------------
# STREAMLIT SETUP
# --------------------------------------------------
st.markdown(
    """
    <div class="app-header">
      <div class="eyebrow">Regulatory Threat Analysis</div>
      <div class="app-header-title">BSI IT-Grundschutz Assistant</div>
      <div class="app-header-sub">Threat identification and VDI&nbsp;2182 risk classification for industrial
      control&nbsp;system components, grounded in the BSI IT-Grundschutz Compendium&nbsp;2022.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------
# SESSION STATE INITIALIZATION
# --------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.image(os.path.join(_HERE, "image.png"), width=265)
st.sidebar.markdown('<div class="side-brand">BSI Assistant</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="side-label">Architecture analysis</div>', unsafe_allow_html=True)
arch = st.sidebar.selectbox(
    "Select architecture",
    ["-- None --"] + list(compositions.keys()),
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.markdown('<div class="status-ok">Assistant connected</div>', unsafe_allow_html=True)
st.sidebar.caption("Grounded in the BSI IT-Grundschutz Compendium 2022")

st.sidebar.markdown("---")
if st.sidebar.button("Clear conversation", use_container_width=True):
    st.session_state.messages = []
    st.session_state.pop("unmatched", None)
    st.session_state.pop("p3_components", None)
    st.rerun()

st.sidebar.markdown("---")
with st.sidebar.expander("How to use", expanded=False):
    st.markdown(
        """
**Chat mode** — no architecture selected
- Ask questions about the compendium. Answers cite their source and are checked for completeness against the official module list.
- Enter component names (e.g. *PLC and Sensor*, *plc_01, plc_02*, *SPS*) to map them to standardized BSI IND modules.
- Unrecognized inputs offer a guided picker to resolve them.
- Select a mapped component and threat to retrieve its description.

**Architecture mode** — select an architecture
- Review the VDI 2182 threat matrix across Confidentiality, Integrity, Availability and Safety, including threats inherited from the general ICS component (IND.2.1).
- Adjust classifications, add expert comments, or add new threat rows.
- Save expert templates and export the matrix as CSV.
        """
    )

st.sidebar.markdown("---")
st.sidebar.link_button(
    "Feedback",
    "https://forms.gle/iEf8MPGVkfR5XuNm6",
    use_container_width=True,
)

# --------------------------------------------------
# PHASE 4–5 UI (Architecture + Expert Customization)
# --------------------------------------------------
if arch != "-- None --":

    # ----------------------------
    # Build base matrix
    # ----------------------------
    df_original = aggregate_threats(arch).set_index("_row_id")
    original_ids = df_original.index.tolist()

    # ---- Layered view: show which modules feed the matrix (incl. inherited)
    _base_modules = compositions[arch]["bsi_modules"]
    _all_modules = expand_modules(_base_modules, inheritance)
    _inherited = [m for m in _all_modules if m not in _base_modules]
    st.markdown(
        '<div class="eyebrow">Risk Matrix</div>'
        '<div class="section-title">VDI 2182 Threat Matrix</div>'
        '<div class="section-sub">Confidentiality &nbsp;·&nbsp; Integrity &nbsp;·&nbsp; '
        'Availability &nbsp;·&nbsp; Safety</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"**Modules:** {', '.join(_base_modules)}"
        + (f"  ·  **inherited:** {', '.join(_inherited)}" if _inherited else "")
    )

    # ---- Summary tiles (dashboard overview)
    _tiles = [
        ("Threats", len(df_original), True),
        ("Confidentiality", int(df_original["C"].sum()), False),
        ("Integrity", int(df_original["I"].sum()), False),
        ("Availability", int(df_original["A"].sum()), False),
        ("Safety", int(df_original["S"].sum()), False),
    ]
    for _col, (_label, _val, _accent) in zip(st.columns(5), _tiles):
        _col.markdown(
            f'<div class="metric-card{" accent" if _accent else ""}">'
            f'<div class="metric-label">{_label}</div>'
            f'<div class="metric-value">{_val}</div></div>',
            unsafe_allow_html=True,
        )

    _ics_threats = [
        t["title"]
        for t in threat_store.get("modules", {}).get("IND.2.1", {}).get("threats", [])
    ]
    if _ics_threats and "IND.2.1" in _all_modules:
        with st.expander("Base ICS-component threats (IND.2.1) — inherited by every ICS component"):
            for _t in _ics_threats:
                st.markdown(f"- {_t}")

    st.markdown(
        '<div class="section-sub" style="margin-top:1.4rem">Edit any cell below. '
        'Use the empty bottom row to add a new expert threat.</div>',
        unsafe_allow_html=True,
    )
    # ----------------------------
    # EDIT MODE (Phase 5)
    # ----------------------------
    edited_df = st.data_editor(
        df_original.reset_index(drop=True),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "C": st.column_config.CheckboxColumn("C"),
            "I": st.column_config.CheckboxColumn("I"),
            "A": st.column_config.CheckboxColumn("A"),
            "S": st.column_config.CheckboxColumn("S"),
            "Comments": st.column_config.TextColumn("Expert Comments"),
            "Origin": st.column_config.TextColumn(disabled=True),
        },
        disabled=["Source Modules"],
        key="vdi_editor"
    )

    # ----------------------------
    # Reattach internal row IDs
    # ----------------------------
    def make_row_id(idx, threat):
        return original_ids[idx] if idx < len(original_ids) else f"EXPERT::{threat}"

    edited_df["_row_id"] = [
        make_row_id(i, t)
        for i, t in enumerate(edited_df["Threat"])
    ]

    edited_df = edited_df.set_index("_row_id", drop=False)

    # ----------------------------
    # Cleanup placeholder rows
    # ----------------------------
    edited_df = edited_df[
        edited_df["Threat"].notna() &
        (edited_df["Threat"].str.strip() != "")
    ].copy()

    # Normalize booleans
    for col in ["C", "I", "A", "S"]:
        edited_df[col] = edited_df[col].fillna(False).astype(bool)

    # Normalize text
    edited_df["Origin"] = edited_df["Origin"].fillna("Expert")
    edited_df["Comments"] = edited_df["Comments"].fillna("")

    # ----------------------------
    # Detect modifications (BSI rows)
    # ----------------------------
    edited_df["Modified"] = False

    common_ids = edited_df.index.intersection(df_original.index)
    for col in ["C", "I", "A", "S", "Comments"]:
        edited_df.loc[common_ids, "Modified"] |= (
            edited_df.loc[common_ids, col]
            != df_original.loc[common_ids, col]
        )

    # ----------------------------
    # Detect NEW expert rows
    # ----------------------------
    new_ids = edited_df.index.difference(df_original.index)
    edited_df.loc[new_ids, "Origin"] = "Expert"
    edited_df.loc[new_ids, "Modified"] = True

    # ----------------------------
    # Status label (audit-safe)
    # ----------------------------
    edited_df["Status"] = edited_df.apply(
        lambda r: "Expert" if r["Origin"] == "Expert"
        else "Modified" if r["Modified"]
        else "BSI",
        axis=1
    )

    # ----------------------------
    # Review View (NO internal IDs)
    # ----------------------------
    st.markdown('<div class="section-title">Final threat matrix</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="legend">'
        '<span><span class="chip chip-bsi"></span>BSI standard</span>'
        '<span><span class="chip chip-mod"></span>Modified by expert</span>'
        '<span><span class="chip chip-exp"></span>Expert-added</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    _review = edited_df.drop(columns=["_row_id"])
    st.dataframe(
        _review.style.apply(_row_style, axis=1),
        use_container_width=True
    )

    # ----------------------------
    # Row provenance (compact, collapsed)
    # ----------------------------
    with st.expander("Row provenance detail"):
        st.dataframe(
            edited_df[["Threat", "Origin", "Status"]],
            use_container_width=True
        )

    # ----------------------------
    # Save Expert Templates
    # ----------------------------
    if st.button("Save expert changes"):
        expert_store[arch] = []
        for _, r in edited_df[edited_df["Origin"] == "Expert"].iterrows():
            expert_store[arch].append({
                "Threat": r["Threat"],
                "CIA_S": [k for k in ["C", "I", "A", "S"] if r[k]],
                "Comments": r["Comments"]
            })
        save_json(EXPERT_STORE_FILE, expert_store)
        st.success("Expert changes saved.")

    # ----------------------------
    # Export CSV
    # ----------------------------
    st.download_button(
        "Download matrix (CSV)",
        edited_df.drop(columns=["_row_id", "Modified"]).to_csv(index=False),
        file_name=f"vdi2182_matrix_{arch}.csv",
        mime="text/csv"
    )

    st.stop()


# ----------------------------
# PHASE 1–3: LLM-BASED INTERACTION
# ----------------------------
# Replay prior conversation so widget reruns (panels below) don't wipe the chat.
for _m in st.session_state.messages:
    with st.chat_message(_m["role"]):
        st.markdown(_m["content"])

user_input = st.chat_input("Ask about BSI IND modules, threats or components...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_Processing…_")

        # New turn: clear any stale interactive-panel state.
        st.session_state.pop("unmatched", None)
        st.session_state.pop("p3_components", None)

        comps = split_components(user_input)
        counts, instances, unmatched = map_to_ind(comps, synonyms)

        # Route to the component mapper only for genuine component input:
        # something actually mapped, or unmatched tokens that look like component
        # identifiers (p_01, RTU…). Questions and greetings ("Hi") go to Q&A.
        go_components = (not looks_like_query(user_input)) and (
            bool(counts) or (bool(unmatched) and is_component_like(comps))
        )
        if go_components:
            parts = [f"**Detected:** {', '.join(f'`{c}`' for c in comps)}"]

            if counts:
                parts.append("**Mapped to standardized components:**")
                for comp_title, n in counts.items():
                    code = code_for_component(comp_title) or "N/A"
                    insts = instances.get(comp_title, [])
                    qty = f"{n}× " if n > 1 else ""
                    extra = f" ({', '.join(insts)})" if len(insts) > 1 else ""
                    parts.append(f"- {qty}{code}: {comp_title}{extra}")

            # Show the mapping summary, then stream each component's threats below.
            placeholder.markdown("\n\n".join(parts))

            for comp_title in counts:
                sub = st.empty()
                text, sources = stream_assistant(
                    f"For component '{comp_title}', return the IND code, module title, "
                    "threat titles (only titles), and citations. "
                    "If missing, reply 'Not found in the BSI Compendium.'",
                    sub,
                    prefix=f"#### {comp_title}\n\n",
                )
                block = [f"#### {comp_title}", text]
                if sources:
                    block.append(f"> Source: {', '.join(sources)}")
                sub.markdown("\n".join(block))
                parts.append("\n".join(block))

            if unmatched:
                tail = (
                    "**Could not auto-map:** "
                    + ", ".join(f"`{u['input']}`" for u in unmatched)
                    + "  — resolve them in the panel below."
                )
                st.markdown("---")
                st.markdown(tail)
                parts.append("---")
                parts.append(tail)

            # Persist for the interactive panels (must survive widget reruns).
            st.session_state["unmatched"] = unmatched
            st.session_state["p3_components"] = list(counts.keys())

            response = "\n\n".join(parts)
            st.session_state.messages.append({"role": "assistant", "content": response})

        else:
            # For general "what/which IND modules" questions, supply the complete
            # authoritative list so the answer is reliably complete (not partial).
            prompt = user_input
            if general_module_question(user_input):
                _listing = "\n".join(f"- {m['code']} {m['title']}" for m in ind_modules)
                prompt = (
                    f"{user_input}\n\n"
                    "Note: the COMPLETE and authoritative set of IND modules in the BSI "
                    "IT-Grundschutz Compendium 2022 is exactly these:\n"
                    f"{_listing}\n"
                    "List ALL of them and give a brief description of each based on the "
                    "document. Do not omit any and do not add modules outside this list. "
                    "Cite the source."
                )
            text, sources = stream_assistant(prompt, placeholder)
            response = text or "No response from assistant."
            if sources:
                response += f"\n\n> Source: {', '.join(sources)}"
            placeholder.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

            # Phase 1: completeness / hallucination check for enumeration questions.
            lower_q = user_input.lower()
            if any(k in lower_q for k in ["all ", "list", "which", "module", "group", "component"]):
                rc = check_completeness(text, ind_modules)
                with st.expander("Completeness check", expanded=True):
                    st.caption(
                        f"{len(rc['present'])}/{len(ind_modules)} authoritative IND modules referenced."
                    )
                    if rc["missing"]:
                        st.warning(
                            "Possibly missing: "
                            + ", ".join(f"{m['code']} {m['title']}" for m in rc["missing"])
                        )
                    if rc["extra"]:
                        st.error(
                            "Codes not in the authoritative list (possible hallucination): "
                            + ", ".join(rc["extra"])
                        )
                    if not rc["missing"] and not rc["extra"]:
                        st.success("All authoritative modules referenced; no out-of-list codes.")

# ----------------------------
# PHASE 2 (case 5) — resolve unmapped components
# ----------------------------
_unmatched = st.session_state.get("unmatched") or []
if _unmatched:
    st.markdown('<div class="section-title">Resolve unmapped components</div>', unsafe_allow_html=True)
    _all_titles = list(synonyms.keys())
    _resolved = {}
    for u in _unmatched:
        options = ["-- skip --"] + (u["candidates"] or _all_titles)
        choice = st.selectbox(f"`{u['input']}` maps to:", options, key=f"dis_{u['input']}")
        if choice != "-- skip --":
            _resolved[u["input"]] = choice
    if _resolved:
        st.success("Resolved → " + ", ".join(f"`{k}` = {v}" for k, v in _resolved.items()))

# ----------------------------
# PHASE 3 — threat description follow-up
# ----------------------------
_p3_components = st.session_state.get("p3_components") or []
if _p3_components:
    st.markdown('<div class="section-title">Threat detail</div>', unsafe_allow_html=True)
    comp_sel = st.selectbox("Component", _p3_components, key="p3_comp")
    titles = titles_for_component(comp_sel)
    if titles:
        threat_sel = st.selectbox("Threat", titles, key="p3_threat")
        if st.button("Get description", key="p3_btn"):
            ph = st.empty()
            text, sources = stream_assistant(
                f"From the BSI IT-Grundschutz Compendium, provide the literal description "
                f"text for the threat titled '{threat_sel}' (in the context of '{comp_sel}'). "
                "Quote the exact text and include the citation. "
                "If it is not present, reply 'Not found in the BSI Compendium.'",
                ph,
            )
            if sources:
                ph.markdown(text + f"\n\n> Source: {', '.join(sources)}")
    else:
        st.info("No stored threat titles for this component yet (regenerate the threat store).")


