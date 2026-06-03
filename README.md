# BSI IT-Grundschutz Assistant

Streamlit app for querying the BSI IT-Grundschutz Compendium via an OpenAI Assistant (file search), mapping industrial components to IND modules, and building VDI 2182 threat matrices with expert customization.

## Features

- **Phase 1–3:** Chat with an OpenAI Assistant backed by the BSI Compendium (file search + citations)
- **Phase 2:** Fuzzy component mapping (PLC, SPS, sensors, etc.) to standardized IND modules
- **Phase 4–5:** Architecture-based threat aggregation and editable VDI 2182 CIA+Safety matrix with CSV export

## Repository layout

```
.
├── streamlit_app.py              # Entry point for Streamlit Cloud
├── bsi_assistant_app_2.py        # Main application
├── populate_threat_store.py      # Optional: refresh threat data from the Assistant
├── requirements.txt
├── .env.example                  # Local env template (do not commit .env)
├── .streamlit/config.toml
└── data/
    ├── synonyms_2022.yaml
    ├── ind_modules_2022.yaml
    ├── component_compositions.yaml
    ├── bsi_threat_store.json
    ├── vdi2182_threat_mapping.yaml
    └── expert_threat_templates.json
```

## Prerequisites

- Python 3.10+
- OpenAI API key
- An OpenAI Assistant with the BSI Compendium PDF attached (file search enabled)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and OPENAI_ASSISTANT_ID
streamlit run bsi_assistant_app_2.py
```

Open http://localhost:8501

## Deploy on Streamlit Cloud (GitHub)

1. **Push this repository to GitHub** (see commands below).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → select your repo, branch `main`, and main file path **`streamlit_app.py`**.
4. Under **Advanced settings → Secrets**, paste:

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_ASSISTANT_ID = "asst_..."
OPENAI_MODEL = "gpt-4o-mini"
```

5. Click **Deploy**. The app rebuilds automatically on every push to the connected branch.

### Notes for cloud deployment

- **Do not commit `.env`** — API keys belong only in Streamlit Secrets (cloud) or local `.env`.
- **Expert template saves** (`Save Expert Changes`) write to `data/expert_threat_templates.json`. On Streamlit Cloud the filesystem is ephemeral, so saves persist only for the current session. Use **Download Matrix (CSV)** for durable exports.
- The BSI PDF lives in your OpenAI vector store (Assistant setup), not in this repo.

## Optional: refresh threat store

Run locally when you need to re-extract threats from the Assistant:

```bash
python populate_threat_store.py
```

Requires `OPENAI_ASSISTANT_ID` in `.env`.

## License

Academic project for educational purposes.
