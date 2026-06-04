# bsi_assistant_app.py
# FINAL VERSION — Phase 1–5
# Phase 1–3: LLM + File Search (BSI reading)
# Phase 4: Architecture-based threat aggregation (deterministic)
# Phase 5: Expert customization (data_editor)

import os
import time
import re
import yaml
import json
import uuid
import streamlit as st
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from rapidfuzz import process, fuzz

# --------------------------------------------------
# ENV + CLIENT
# --------------------------------------------------
load_dotenv()
client = OpenAI()

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

SYNONYMS_FILE = "data/synonyms_2022.yaml"
IND_MODULES_FILE = "data/ind_modules_2022.yaml"
COMPOSITIONS_FILE = "data/component_compositions.yaml"
THREAT_STORE_FILE = "data/bsi_threat_store.json"
VDI_MAPPING_FILE = "data/vdi2182_threat_mapping.yaml"
EXPERT_STORE_FILE = "data/expert_threat_templates.json"

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
compositions = load_yaml(COMPOSITIONS_FILE).get("compositions", {})
threat_store = load_json(THREAT_STORE_FILE, {"modules": {}})
expert_store = load_json(EXPERT_STORE_FILE, {})
vdi_mapping = load_yaml(VDI_MAPPING_FILE).get("mappings", {})

title_lookup = {t.lower(): t for t in synonyms.keys()}

# ----------------------------
# THREAT AGGREGATION ENGINE
# ----------------------------
def aggregate_threats(composition_id, compositions, threat_store):
    modules = compositions[composition_id]["bsi_modules"]
    aggregated = {}

    for module in modules:
        module_data = threat_store.get("modules", {}).get(module)
        if not module_data:
            continue

        for threat in module_data.get("threats", []):
            title = threat["title"]
            if title not in aggregated:
                aggregated[title] = {
                    "threat_id": threat["threat_id"],
                    "title": title,
                    "source_modules": [module],
                    "citation": threat["citation"]
                }
            else:
                aggregated[title]["source_modules"].append(module)

    return list(aggregated.values())

# ----------------------------
# HELPER FUNCTIONS (PHASE 2)
# ----------------------------
def split_components(text):
    if not text:
        return []
    parts = re.split(r"[;,\n]+| and ", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]

def map_to_ind(components):
    matched, unmatched = [], []
    all_names = []
    for title, syns in synonyms.items():
        all_names.append(title.lower())
        all_names.extend([s.lower() for s in syns])

    for comp in components:
        comp_lower = comp.lower().strip()
        if re.search(r"\b(plc|sps)\b", comp_lower) or re.match(r"^plc[_\-]?\w+", comp_lower):
            matched.append("Programmable Logic Controller (PLC)")
            continue
        if comp_lower in title_lookup:
            matched.append(title_lookup[comp_lower])
            continue
        best = process.extractOne(comp_lower, all_names, scorer=fuzz.token_set_ratio)
        if best and best[1] >= 86:
            for title, syns in synonyms.items():
                if best[0] == title.lower() or best[0] in [s.lower() for s in syns]:
                    matched.append(title)
                    break
        else:
            unmatched.append(comp)

    return matched, unmatched

# ----------------------------
# THREAT AGGREGATION
# ----------------------------
def aggregate_threats(arch_id):
    aggregated = {}

    # ---- BSI threats
    for mod in compositions[arch_id]["bsi_modules"]:
        mod_data = threat_store["modules"].get(mod)
        if not mod_data:
            continue

        for t in mod_data["threats"]:
            title = t["title"]
            row_id = f"BSI::{title}"

            if row_id not in aggregated:
                aggregated[row_id] = {
                    "_row_id": row_id,
                    "Threat": title,
                    "Source Modules": [mod],
                    "C": False,
                    "I": False,
                    "A": False,
                    "S": False,
                    "Origin": "BSI",
                    "Comments": "",
                    "Modified": False
                }
            else:
                aggregated[row_id]["Source Modules"].append(mod)

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

# --------------------------------------------------
# STREAMLIT SETUP
# --------------------------------------------------
st.set_page_config(page_title="🔒 BSI IT-Grundschutz Assistant", layout="wide")
st.title("🔒 BSI IT-Grundschutz Assistant")
st.caption("Phase 1–5: BSI → Architecture → Expert Customization")

# --------------------------------------------------
# SESSION STATE INITIALIZATION  ✅ FIX
# --------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.markdown("## 🧠 Architecture Analysis")
arch = st.sidebar.selectbox(
    "Select architecture",
    ["-- None --"] + list(compositions.keys())
)

st.sidebar.markdown("---")
st.sidebar.success("Assistant Loaded")
st.sidebar.info(f"Assistant ID: {ASSISTANT_ID}")

st.sidebar.markdown("---")
with st.sidebar.expander("How to use", expanded=False):
    st.markdown(
        """
**Chat mode** — no architecture selected
- Ask questions about BSI IND modules, threats, or components. Answers cite sources from the compendium.
- Enter component names (e.g. *PLC and Sensor*, *plc_01, plc_02*, *SPS*) to map them to standardized BSI IND modules and retrieve threat information per component.
- Unmapped components are listed in the assistant response.

**Architecture mode** — select an architecture
- Review the VDI 2182 threat matrix across Confidentiality, Integrity, Availability and Safety.
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

    st.markdown("## 📊 VDI 2182 Threat Matrix (CIA + Safety)")

    st.caption("ℹ️ Use the empty row at the bottom to add new expert threats.")
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
    # 🔐 REATTACH INTERNAL ROW IDs (CORRECT)
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
        lambda r: "🔵 Expert" if r["Origin"] == "Expert"
        else "🟡 Modified" if r["Modified"]
        else "🟢 BSI",
        axis=1
    )

    # ----------------------------
    # Review View (NO internal IDs)
    # ----------------------------
    st.markdown("### 📋 Final Threat Matrix (Review View)")
    st.dataframe(
        edited_df.drop(columns=["_row_id"]),
        use_container_width=True
    )

    # ----------------------------
    # Status Overview
    # ----------------------------
    st.markdown("### 🏷️ Row Status")
    st.dataframe(
        edited_df[["Threat", "Origin", "Status"]],
        use_container_width=True
    )

    # ----------------------------
    # Save Expert Templates
    # ----------------------------
    if st.button("💾 Save Expert Changes"):
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
        "⬇️ Download Matrix (CSV)",
        edited_df.drop(columns=["_row_id", "Modified"]).to_csv(index=False),
        file_name=f"vdi2182_matrix_{arch}.csv",
        mime="text/csv"
    )

    st.stop()


# ----------------------------
# PHASE 1–3: LLM-BASED INTERACTION
# ----------------------------
user_input = st.chat_input("Ask about BSI IND modules, threats or components...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("⏳ Processing...")

        comps = split_components(user_input)
        mapped, unmapped = map_to_ind(comps)

        if mapped:
            final_parts = []
            final_parts.append(f"🔍 **Detected:** {', '.join([f'`{c}`' for c in comps])}")
            final_parts.append("**Mapped to standardized components:**")

            unique = list(dict.fromkeys(mapped))
            for comp in unique:
                code = next((m.get("code") for m in ind_modules if m.get("title") == comp), "N/A")
                final_parts.append(f"- {code}: {comp}")

            for comp in unique:
                query = (
                    f"For component '{comp}', return the IND code, module title, threat titles (only titles), "
                    "and citations. If missing, reply 'Not found in the BSI Compendium.'"
                )

                thread = client.beta.threads.create()
                client.beta.threads.messages.create(thread_id=thread.id, role="user", content=query)
                run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)

                while run.status not in ["completed", "failed"]:
                    time.sleep(0.8)
                    run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

                messages = client.beta.threads.messages.list(thread_id=thread.id)
                latest = next((m for m in messages.data if m.role == "assistant"), None)

                comp_parts = [f"### 📘 {comp}"]
                if latest:
                    for item in latest.content:
                        if item.type == "text":
                            comp_parts.append(item.text.value)
                            for ann in getattr(item.text, "annotations", []) or []:
                                if ann.type == "file_citation":
                                    quote = getattr(ann, "text", "").strip()
                                    if quote:
                                        comp_parts.append(f"\n> 📚 **Source:** \"{quote[:300]}...\"\n")

                final_parts.append("\n".join(comp_parts))

            if unmapped:
                final_parts.append("---")
                final_parts.append(f"⚠️ **Could not map:** {', '.join([f'`{c}`' for c in unmapped])}")

            response = "\n\n".join(final_parts)
            placeholder.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

        else:
            thread = client.beta.threads.create()
            client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_input)
            run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)

            while run.status not in ["completed", "failed"]:
                time.sleep(0.8)
                run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            messages = client.beta.threads.messages.list(thread_id=thread.id)
            latest = next((m for m in messages.data if m.role == "assistant"), None)

            parts = []
            if latest:
                for item in latest.content:
                    if item.type == "text":
                        parts.append(item.text.value)
                        for ann in getattr(item.text, "annotations", []) or []:
                            if ann.type == "file_citation":
                                quote = getattr(ann, "text", "").strip()
                                if quote:
                                    parts.append(f"\n> **Source:** \"{quote[:300]}...\"\n")

            response = "\n\n".join(parts) if parts else "No response from assistant."
            placeholder.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

# ----------------------------
# CLEAR CHAT
# ----------------------------
if st.button("🗑️ Clear Chat"):
    st.session_state.messages = []
    st.rerun()

