"""engine/logic.py — Pure, deterministic logic for the BSI assistant.

No Streamlit / OpenAI imports here on purpose: everything is unit-testable.

Covers:
  * Phase 2  — component parsing + mapping (incl. instance counting and
               disambiguation candidates for unmappable inputs)
  * Phase 4  — module inheritance ("a PLC is also an ICS component")
  * Phase 1  — completeness / hallucination check vs the authoritative list
"""

import re
from rapidfuzz import process, fuzz

PLC_CANONICAL = "Programmable Logic Controller (PLC)"
DEFAULT_THRESHOLD = 86


# --------------------------------------------------
# PHASE 2 — component parsing + mapping
# --------------------------------------------------
def split_components(text):
    """Split a free-text component list on ; , newlines or the word 'and'."""
    if not text:
        return []
    parts = re.split(r"[;,\n]+| and ", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


QUESTION_WORDS = {
    "which", "what", "how", "why", "when", "where", "who", "explain",
    "describe", "tell", "show", "list", "does", "do", "is", "are", "can",
    "give", "provide", "summarize", "summarise", "define", "name",
}


def looks_like_query(text):
    """Heuristic: is this a natural-language question (route to the LLM) rather
    than a list of component names (route to the mapper)?

    True if it contains '?', starts with a question/enumeration word, or is
    longer than 6 words. Keeps short token lists like "PLC and Sensor" or
    "p_01" on the component-mapping path.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    if "?" in t:
        return True
    first = re.split(r"\W+", t, maxsplit=1)[0]
    if first in QUESTION_WORDS:
        return True
    return len(t.split()) > 6


def general_module_question(text):
    """True for a GENERAL question about the IND module set (so we can supply
    the complete authoritative list), but NOT for a question about one specific
    module (e.g. 'what is IND.2.2?')."""
    low = (text or "").lower()
    if re.search(r"ind\.\d", low):           # a specific module code -> not general
        return False
    mentions_set = ("module" in low) or ("ind" in low and ("component" in low or "group" in low))
    if not mentions_set:
        return False
    return any(k in low for k in (
        "what", "which", "list", "all", "available", "overview", "explain", "are", "tell", "name",
    ))


def is_component_like(tokens):
    """Heuristic: do these look like component identifiers rather than plain
    words/greetings? Component identifiers usually contain a digit or _/-, or
    are short all-caps codes (PLC, RTU, HMI, SPS). 'Hi'/'hello' are NOT.
    Only consulted when nothing mapped, to decide mapper-vs-chat routing.
    """
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if re.search(r"[\d_\-]", t):
            return True
        if t.isupper() and re.fullmatch(r"[A-Z]{2,6}", t):
            return True
    return False


def build_name_index(synonyms):
    """Map every lowercased canonical title and synonym -> canonical title."""
    index = {}
    for title, syns in synonyms.items():
        index[title.lower()] = title
        for s in syns or []:
            index[s.lower()] = title
    return index


def map_component(comp, synonyms, name_index=None, threshold=DEFAULT_THRESHOLD):
    """Map a single raw component string.

    Returns (canonical_title_or_None, candidates). When no confident match is
    found, ``candidates`` holds the best-guess canonical titles for the user
    to choose from (Phase-2 case 5: "p_01").
    """
    if name_index is None:
        name_index = build_name_index(synonyms)

    comp_lower = comp.lower().strip()

    # PLC rule: explicit word, or an instance name like "plc_01".
    if re.search(r"\b(plc|sps)\b", comp_lower) or re.match(r"^plc[_\-]?\w+", comp_lower):
        return PLC_CANONICAL, []

    # Exact canonical / synonym hit.
    if comp_lower in name_index:
        return name_index[comp_lower], []

    # Fuzzy match.
    all_names = list(name_index.keys())
    matches = process.extract(comp_lower, all_names, scorer=fuzz.token_set_ratio, limit=5)
    if matches and matches[0][1] >= threshold:
        return name_index[matches[0][0]], []

    # No confident match -> de-duplicated candidate canonical titles.
    candidates = []
    for name, _score, _ in matches:
        cand = name_index[name]
        if cand not in candidates:
            candidates.append(cand)
    return None, candidates


def map_to_ind(components, synonyms, threshold=DEFAULT_THRESHOLD):
    """Map a list of raw components.

    Returns:
      counts:    {canonical_title: count}            (Phase-2 case 4: 2x PLC)
      instances: {canonical_title: [raw inputs...]}
      unmatched: [{"input": str, "candidates": [titles]}]  (Phase-2 case 5)
    """
    name_index = build_name_index(synonyms)
    counts, instances, unmatched = {}, {}, []

    for comp in components:
        canonical, candidates = map_component(comp, synonyms, name_index, threshold)
        if canonical:
            counts[canonical] = counts.get(canonical, 0) + 1
            instances.setdefault(canonical, []).append(comp)
        else:
            unmatched.append({"input": comp, "candidates": candidates})

    return counts, instances, unmatched


# --------------------------------------------------
# PHASE 4 — module inheritance
# --------------------------------------------------
def expand_modules(module_list, inheritance):
    """Expand BSI module codes with their inherited parents.

    ``inheritance`` maps child_code -> [parent_codes]. Used to model that a
    specific ICS component (e.g. IND.2.2 PLC) also carries the threats of the
    general ICS-component module (IND.2.1). Parents are appended (deduped) so
    original ordering is preserved and inherited modules are clearly trailing.
    """
    result = list(module_list)
    for mod in module_list:
        for parent in inheritance.get(mod, []) or []:
            if parent not in result:
                result.append(parent)
    return result


# --------------------------------------------------
# PHASE 1 — completeness / hallucination check
# --------------------------------------------------
IND_CODE_RE = re.compile(r"IND\.\d+(?:\.\d+)*", re.IGNORECASE)


def check_completeness(answer_text, ground_truth):
    """Compare an LLM enumeration answer against the authoritative IND list.

    ``ground_truth`` is a list of {"code", "title"} dicts. A module counts as
    present if its code OR its title appears in the answer. Returns present /
    missing modules plus any IND codes mentioned that are NOT in ground truth
    (potential hallucinations).
    """
    text = (answer_text or "").lower()
    present, missing = [], []
    for m in ground_truth:
        code = str(m.get("code", "")).lower()
        title = str(m.get("title", "")).lower()
        if (code and code in text) or (title and title in text):
            present.append(m)
        else:
            missing.append(m)

    gt_codes = {str(m.get("code", "")).upper() for m in ground_truth if m.get("code")}
    mentioned = {c.upper() for c in IND_CODE_RE.findall(answer_text or "")}
    extra = sorted(mentioned - gt_codes)

    return {"present": present, "missing": missing, "extra": extra}
