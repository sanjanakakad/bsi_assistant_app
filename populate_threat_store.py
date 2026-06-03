#!/usr/bin/env python3
"""
populate_threat_store.py — Extract BSI threat titles per IND module via the
OpenAI Assistant (File Search) and write a CLEAN data/bsi_threat_store.json.

Why this rewrite:
  The previous version stored each raw assistant text block as a single threat
  "title", so titles ended up containing citation markers (【4:1†...】),
  "Sources:" footers, and even the literal string "Not found in the BSI
  Compendium." This version parses the answer into individual, cleaned titles.

Run from the "File Search" directory with the project venv:
  /Users/aditya/Work/Namasys/Self\\ Study/BSI\\ RAG/.venv/bin/python populate_threat_store.py
"""

import os
import re
import json
import time
import sys
from datetime import datetime, timezone

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
THREAT_STORE_FILE = "data/bsi_threat_store.json"

# All modules referenced by data/component_compositions.yaml.
# IND.2.1 (General ICS Components) is required for Phase-4 "a PLC is also an
# ICS component" inheritance.
TARGET_MODULES = {
    "IND.2.1": "General ICS Components",
    "IND.2.2": "Programmable Logic Controller (PLC)",
    "IND.2.3": "Sensors and Actuators",
    "IND.2.4": "Machine",
    "IND.2.7": "Safety Instrumented Systems",
    "IND.3.2": "Remote Maintenance in Industry",
}

# Citation markers the file_search tool injects, e.g. 【4:1†bsi_it_gs_comp_2022.pdf】
MARKER_RE = re.compile(r"【[^】]*】|\[[^\]]*†[^\]]*\]")
NOT_FOUND = "not found in the bsi"


def clean_title(raw: str) -> str:
    """Strip citation markers, leading bullets/numbering, and whitespace."""
    s = MARKER_RE.sub("", raw)
    s = s.strip()
    s = re.sub(r"^[\-\*•‣◦\d\.\)\s]+", "", s)  # bullets / "1) " / "1. "
    s = re.sub(r"\s+", " ", s).strip().strip('"').strip()
    return s


def is_noise(title: str) -> bool:
    low = title.lower()
    if not low:
        return True
    if low.startswith("source"):
        return True
    if NOT_FOUND in low:
        return True
    if low.endswith(":"):           # section headers, e.g. "Here are the threats:"
        return True
    if re.fullmatch(r"[\w\-]+\.pdf", low):  # bare filename (Sources section)
        return True
    if low in {"threats", "threat titles", "titles", "sources"}:
        return True
    return False


def parse_titles(text: str) -> list:
    """Parse assistant output into a clean, de-duplicated list of titles.

    Strategy: prefer a JSON array if present; otherwise fall back to one
    title per line. Both paths are cleaned and noise-filtered.
    """
    parsed = None  # None => no JSON array found; list => found (possibly empty)

    # 1) JSON array, e.g. ["Manipulation of hardware or software", ...].
    #    Strip ```json fences first; a non-greedy [...] avoids grabbing trailing
    #    prose. An empty array [] is a VALID "no threats" answer and must NOT
    #    fall through to the line-based parser.
    fenced = re.sub(r"```(?:json)?", "", text)
    m = re.search(r"\[.*?\]", fenced, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                parsed = [str(x) for x in arr]
        except Exception:
            parsed = None

    if parsed is not None:
        titles = parsed
    else:
        # 2) Fallback: line-by-line, stopping at any "Sources" section.
        titles = []
        for raw in text.splitlines():
            if clean_title(raw).lower().startswith("source"):
                break  # everything after is the citation list
            titles.append(raw)

    cleaned, seen = [], set()
    for t in titles:
        t = clean_title(t)
        if is_noise(t):
            continue
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        cleaned.append(t)
    return cleaned


def ask_assistant(module_code: str, module_name: str) -> str:
    """Run a single-shot thread against the assistant and return its text."""
    prompt = (
        f"List all official threat titles defined for module {module_code} "
        f"({module_name}) in the BSI IT-Grundschutz Compendium. "
        "Return ONLY the official threat titles exactly as written, as a JSON "
        'array of strings, e.g. ["Title one", "Title two"]. '
        "Do not include descriptions, numbering, or any prose. "
        'If the module defines no module-specific threats, return [].'
    )

    thread = client.beta.threads.create()
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)

    deadline = 120  # seconds
    waited = 0
    while run.status not in ("completed", "failed", "cancelled", "expired"):
        time.sleep(1)
        waited += 1
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if waited >= deadline:
            break

    if run.status != "completed":
        print(f"  ! run status: {run.status} — skipping", file=sys.stderr)
        return ""

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assistant_msg = next((m for m in messages.data if m.role == "assistant"), None)
    if not assistant_msg:
        return ""

    return "\n".join(
        item.text.value for item in assistant_msg.content if item.type == "text"
    )


def main() -> int:
    if not ASSISTANT_ID:
        print("ERROR: OPENAI_ASSISTANT_ID not set in .env", file=sys.stderr)
        return 1

    store = {
        "metadata": {
            "source": "BSI IT-Grundschutz Compendium 2022",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "extraction_method": "OpenAI Assistant + File Search (JSON titles, cleaned)",
            "notes": "Threat titles parsed and cleaned; citation markers stripped.",
        },
        "modules": {},
    }

    for code, name in TARGET_MODULES.items():
        print(f"\n🔍 Extracting threats for {code} — {name}")
        text = ask_assistant(code, name)
        titles = parse_titles(text)

        threats = []
        for i, title in enumerate(titles, start=1):
            threats.append({
                "threat_id": f"T_{code.replace('.', '_')}_{i:02d}",
                "title": title,
                "description": None,
                "citation": {
                    "file": "bsi_it_gs_comp_2022.pdf",
                    "quote": title,
                },
            })

        store["modules"][code] = {"module_title": name, "threats": threats}
        print(f"  ✅ stored {len(threats)} threat(s)")
        for t in threats:
            print(f"     - {t['title']}")

    os.makedirs(os.path.dirname(THREAT_STORE_FILE), exist_ok=True)
    with open(THREAT_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Wrote {THREAT_STORE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
