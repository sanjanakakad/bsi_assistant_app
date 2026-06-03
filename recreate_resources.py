#!/usr/bin/env python3
"""
recreate_resources.py — Recreate the deleted OpenAI Vector Store + Assistant
for the BSI IT-Grundschutz RAG app, and update .env in place.

Mirrors the canonical config in setup_assistant.py (model=gpt-4o, file_search,
strict-grounding MASTER_PROMPT) but adds two safety fixes:
  1) Waits until the PDF is fully indexed in the vector store before finishing.
  2) Replaces the OPENAI_VECTOR_STORE_ID / OPENAI_ASSISTANT_ID lines in .env
     instead of appending duplicates.

Run from the "File Search" directory with the project venv:
  /Users/aditya/Work/Namasys/Self\\ Study/BSI\\ RAG/.venv/bin/python recreate_resources.py
"""

import os
import re
import sys
import shutil
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
PDF_PATH = os.path.join(HERE, "pdfs", "bsi_it_gs_comp_2022.pdf")

VECTOR_STORE_NAME = "BSI_Compendium_Store"
ASSISTANT_NAME = "BSI Security Assistant (Strict Grounding)"
MODEL = "gpt-4o"

MASTER_PROMPT = """
You are a BSI IT-Grundschutz Compendium Expert trained to operate ONLY on the user-uploaded BSI IT-Grundschutz Compendium PDF via the File Search tool.

ABSOLUTE RULES:
1. You must use ONLY information contained in the retrieved PDF chunks.
2. You must NEVER use outside knowledge (ICS, PLCs, OT/IT security, automation, electronics, etc.).
3. You must NEVER guess, infer, generalize, assume, or logically expand beyond the PDF text.
4. If the PDF does NOT explicitly contain the answer, respond exactly with:
     "Not found in the BSI Compendium."
5. All statements MUST be supported by a source snippet from the retrieved PDF chunks.
6. If a statement is not supported by a retrieved chunk, OMIT IT.
7. Never fabricate modules, threats, IND codes, or component names.
8. Never rewrite or reinterpret the meaning of PDF text. Stay literal.

TOOL USE RULES:
- You must rely strictly on the retrieved chunks from the File Search tool.
- If the retrieved chunks do not appear complete (e.g., only partial list), do NOT produce a complete list.
- Instead reply:
     "Not enough information retrieved. Please rephrase your query."

PHASE 1 — STRUCTURAL QUERIES:
- For any request to list IND modules, threats, structure:
  • Only return EXACT items shown in retrieved chunks.
  • If retrieval incomplete: "Not enough information retrieved. Please rephrase your query."

PHASE 2 — COMPONENT MAPPING:
- Synonym mapping (PLC, SPS, S7 etc.) is performed externally.
- Treat all user component names as already canonicalized.
- Return:
  • IND code
  • Module title
  • Exact PDF text (quoted) with citations
- If not found: "Not found in the BSI Compendium."

PHASE 3 — THREAT EXTRACTION:
- When asked to "list threats": titles only.
- When asked for "details": return literal text.
- If module has no module-specific threats:
    "The BSI Compendium does not assign module-specific threat titles for this module."

FORMATTING:
- Use bullet points.
- Every bullet must include a citation.
- Always end with a Sources section.
"""


def update_env(env_path: str, updates: dict) -> None:
    """Replace existing uncommented KEY=... lines; append any missing keys."""
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    remaining = dict(updates)
    out = []
    for line in lines:
        replaced = False
        for key, val in updates.items():
            # match an uncommented assignment for this key (ignore '# KEY=' lines)
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                out.append(f"{key}={val}\n")
                remaining.pop(key, None)
                replaced = True
                break
        if not replaced:
            out.append(line)

    # append any keys that were not present at all
    if remaining:
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        for key, val in remaining.items():
            out.append(f"{key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(out)


def main() -> int:
    load_dotenv(ENV_PATH)

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set in .env", file=sys.stderr)
        return 1
    if not os.path.exists(PDF_PATH):
        print(f"ERROR: PDF not found at {PDF_PATH}", file=sys.stderr)
        return 1

    client = OpenAI()

    # ---- 1) Create the vector store ----
    print(f"Creating vector store '{VECTOR_STORE_NAME}' ...")
    vector_store = client.beta.vector_stores.create(name=VECTOR_STORE_NAME)
    print(f"  vector store id: {vector_store.id}")

    # ---- 2) Upload the PDF and WAIT until it is indexed ----
    print(f"Uploading + indexing {os.path.basename(PDF_PATH)} (this can take a minute) ...")
    with open(PDF_PATH, "rb") as fh:
        batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=[fh],
        )
    print(f"  batch status: {batch.status}")
    print(f"  file counts:  {batch.file_counts}")
    if batch.status != "completed" or batch.file_counts.failed:
        print("ERROR: PDF indexing did not complete cleanly. Aborting before assistant creation.",
              file=sys.stderr)
        return 2

    # ---- 3) Create the assistant ----
    print(f"Creating assistant '{ASSISTANT_NAME}' (model={MODEL}) ...")
    assistant = client.beta.assistants.create(
        name=ASSISTANT_NAME,
        instructions=MASTER_PROMPT,
        model=MODEL,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
    )
    print(f"  assistant id: {assistant.id}")

    # ---- 4) Update .env (backup first, then replace the dead ID lines) ----
    backup = f"{ENV_PATH}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(ENV_PATH, backup)
    print(f"Backed up .env -> {os.path.basename(backup)}")
    update_env(ENV_PATH, {
        "OPENAI_VECTOR_STORE_ID": vector_store.id,
        "OPENAI_ASSISTANT_ID": assistant.id,
    })
    print("Updated .env with new IDs.")

    print("\n✅ Done. New resources:")
    print(f"OPENAI_VECTOR_STORE_ID={vector_store.id}")
    print(f"OPENAI_ASSISTANT_ID={assistant.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
