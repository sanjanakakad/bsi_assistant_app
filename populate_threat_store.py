import json
import time
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
THREAT_STORE_FILE = "data/bsi_threat_store.json"

TARGET_MODULES = {
    "IND.2.3": "Sensors and Actuators",
    "IND.2.4": "Machine",
    "IND.3.3": "Industrial Monitoring and Logging"
}

def load_store():
    try:
        with open(THREAT_STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"modules": {}}

def save_store(store):
    with open(THREAT_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

store = load_store()

for module_code, module_name in TARGET_MODULES.items():
    print(f"\n🔍 Extracting threats for {module_code} — {module_name}")

    prompt = (
        f"List all threat titles defined for module {module_code} "
        f"({module_name}) in the BSI IT-Grundschutz Compendium. "
        "Return ONLY the official threat titles exactly as written. "
        "Include citations."
    )

    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=prompt
    )

    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID
    )

    while run.status not in ["completed", "failed"]:
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assistant_msg = next(m for m in messages.data if m.role == "assistant")

    threats = []

    for item in assistant_msg.content:
        if item.type == "text":
            title = item.text.value.strip()
            threats.append({
                "threat_id": f"T_{module_code}_{len(threats)+1:02}",
                "title": title,
                "description": None,
                "citation": {
                    "file": "bsi_it_gs_comp_2022.pdf",
                    "quote": title
                }
            })

    store["modules"][module_code] = {
        "module_title": module_name,
        "threats": threats
    }

    save_store(store)
    print(f"✅ Stored {len(threats)} threats for {module_code}")

print("\n🎉 Threat store population complete.")
