"""Tests for engine/logic.py — Phase 1/2/4 deterministic logic.

Run: pytest -q   (from the "File Search" directory)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.logic import (
    split_components,
    map_to_ind,
    map_component,
    expand_modules,
    check_completeness,
    looks_like_query,
    is_component_like,
    general_module_question,
    PLC_CANONICAL,
)

# Mirrors data/synonyms_2022.yaml
SYNONYMS = {
    "Programmable Logic Controller (PLC)": ["plc", "sps", "s7", "siemens s7", "controller"],
    "Sensors and Actuators": ["sensor", "sensors", "actuator", "actuators"],
    "Machine": ["machine", "robot", "cnc"],
    "Remote Maintenance": ["remote maintenance", "remote access", "vpn access"],
}

SENSOR = "Sensors and Actuators"


# ---- split_components ----
def test_split_on_and():
    assert split_components("PLC and Sensor") == ["PLC", "Sensor"]


def test_split_on_commas():
    assert split_components("plc_01, plc_02") == ["plc_01", "plc_02"]


# ---- Phase 2: the five required cases ----
def test_case1_plc():
    counts, _, unmatched = map_to_ind(["PLC"], SYNONYMS)
    assert counts == {PLC_CANONICAL: 1}
    assert unmatched == []


def test_case2_plc_and_sensor():
    counts, _, unmatched = map_to_ind(split_components("PLC and Sensor"), SYNONYMS)
    assert counts.get(PLC_CANONICAL) == 1
    assert counts.get(SENSOR) == 1
    assert unmatched == []


def test_case3_german_sps():
    counts, _, _ = map_to_ind(["SPS"], SYNONYMS)
    assert counts == {PLC_CANONICAL: 1}


def test_case4_two_plc_instances():
    counts, instances, _ = map_to_ind(["plc_01", "plc_02"], SYNONYMS)
    assert counts == {PLC_CANONICAL: 2}                       # <-- count preserved
    assert instances[PLC_CANONICAL] == ["plc_01", "plc_02"]


def test_case5_ambiguous_returns_candidates():
    counts, _, unmatched = map_to_ind(["p_01"], SYNONYMS)
    assert counts == {}
    assert len(unmatched) == 1
    assert unmatched[0]["input"] == "p_01"
    assert isinstance(unmatched[0]["candidates"], list)       # suggestions offered


# ---- query vs component routing ----
def test_question_is_query():
    assert looks_like_query("Which IND modules are defined in the BSI compendium?")
    assert looks_like_query("List all threats for PLC")
    assert looks_like_query("What is a sensor")


def test_component_input_is_not_query():
    assert not looks_like_query("PLC")
    assert not looks_like_query("PLC and Sensor")
    assert not looks_like_query("plc_01, plc_02")
    assert not looks_like_query("p_01")


def test_greeting_not_component_like():
    assert not is_component_like(["Hi"])
    assert not is_component_like(["hello"])
    assert not is_component_like(["thanks"])


def test_identifiers_are_component_like():
    assert is_component_like(["p_01"])
    assert is_component_like(["plc_02"])
    assert is_component_like(["RTU"])
    assert is_component_like(["HMI"])


def test_general_module_question():
    assert general_module_question("what is an IND module")
    assert general_module_question("which IND modules are available")
    assert general_module_question("list all IND components")


def test_specific_or_unrelated_not_general_module_question():
    assert not general_module_question("what is IND.2.2")          # specific code
    assert not general_module_question("what threats apply to IND.2.4")
    assert not general_module_question("what is a PLC")            # no module/ind+component term


# ---- Phase 4: inheritance ----
def test_plc_inherits_general_ics():
    inheritance = {"IND.2.2": ["IND.2.1"], "IND.2.3": ["IND.2.1"]}
    assert expand_modules(["IND.2.2"], inheritance) == ["IND.2.2", "IND.2.1"]


def test_inheritance_dedups():
    inheritance = {"IND.2.2": ["IND.2.1"], "IND.2.3": ["IND.2.1"]}
    out = expand_modules(["IND.2.2", "IND.2.3"], inheritance)
    assert out == ["IND.2.2", "IND.2.3", "IND.2.1"]           # IND.2.1 only once


def test_no_inheritance_passthrough():
    assert expand_modules(["IND.3.1"], {}) == ["IND.3.1"]


# ---- Phase 1: completeness / hallucination ----
GROUND_TRUTH = [
    {"code": "IND.2.1", "title": "General ICS Components"},
    {"code": "IND.2.2", "title": "Programmable Logic Controller (PLC)"},
    {"code": "IND.2.3", "title": "Sensors and Actuators"},
]


def test_completeness_all_present():
    answer = "We have IND.2.1, IND.2.2 and IND.2.3."
    r = check_completeness(answer, GROUND_TRUTH)
    assert r["missing"] == []
    assert r["extra"] == []
    assert len(r["present"]) == 3


def test_completeness_flags_missing():
    answer = "Only IND.2.2 is relevant."
    r = check_completeness(answer, GROUND_TRUTH)
    missing_codes = {m["code"] for m in r["missing"]}
    assert missing_codes == {"IND.2.1", "IND.2.3"}


def test_completeness_flags_hallucination():
    answer = "Modules: IND.2.1, IND.2.2, IND.2.3, IND.9.9 (made up)."
    r = check_completeness(answer, GROUND_TRUTH)
    assert "IND.9.9" in r["extra"]


def test_completeness_matches_by_title():
    answer = "The General ICS Components, the Programmable Logic Controller (PLC), and Sensors and Actuators."
    r = check_completeness(answer, GROUND_TRUTH)
    assert r["missing"] == []
