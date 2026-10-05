"""Deterministic AI regressions; no model or external network is used here."""

import asyncio
import copy
import json

import pytest
from agents.tool_context import ToolContext

from backend.ai import agent as service
from backend.ai import chatbot
from backend.ai.rag import retrieve_safety
from backend.ai.severity_model import load_examples, predict_severity
from backend.ai.agent import check_alerts, find_duplicates, list_available_teams, report_tools


@pytest.mark.parametrize("message", [
    "Two children are trapped inside a flooded house.",
    "A person is drowning and needs immediate assistance.",
    "An unconscious resident cannot breathe.",
    "രണ്ട് കുട്ടികൾ വീട്ടിൽ കുടുങ്ങിയിരിക്കുന്നു. രക്ഷിക്കണം.",
])
def test_danger_escalation_is_high_including_malayalam(message):
    result = predict_severity(message)
    assert result["severity"] == "HIGH"
    assert result["danger_flag"] is True
    assert result["severity_source"] == "conservative_danger_escalation"
    assert "Synthetic" in result["model_notice"]
    assert result["confidence_kind"] == "uncalibrated_synthetic_classifier_probability"


def test_unknown_vocabulary_does_not_imply_low_or_fabricated_confidence():
    result = predict_severity("zxqvwyplmrt zbyqzxpl")
    assert result["severity"] == "MODERATE"
    assert result["confidence"] is None
    assert result["vocabulary_recognized"] is False


def test_training_data_explicitly_synthetic_and_has_three_labels():
    rows = load_examples()
    assert {row["severity"] for row in rows} == {"LOW", "MODERATE", "HIGH"}
    assert {row["source"] for row in rows} == {"synthetic_demo"}


def alert(**changes):
    return {"id": 1, "active": True, "district": "Alappuzha", "location": "Chengannur", "expires_at": "2099-01-01T00:00:00Z", **changes}


def test_alert_match_case_insensitive_and_unexpired():
    result = check_alerts("CHENGANNUR town", "alappuzha", [alert()])
    assert result["status"] == "MATCH"
    assert result["matched_alert_ids"] == [1]


@pytest.mark.parametrize("changes", [
    {"expires_at": "2000-01-01T00:00:00Z"},
    {"active": False},
    {"district": "Ernakulam"},
    {"location": "Aluva"},
])
def test_expired_inactive_and_other_place_alerts_do_not_match(changes):
    result = check_alerts("Chengannur", "Alappuzha", [alert(**changes)])
    assert result["status"] == "NO_MATCH"
    assert "does not mean the report is false" in result["reason"]


@pytest.mark.parametrize("location,district,alerts", [
    ("", "Alappuzha", [alert()]),
    ("Chengannur", "", [alert()]),
    ("Chengannur", "Alappuzha", [alert(expires_at="invalid date")]),
    ("Chengannur", "Alappuzha", [alert(location="")]),
])
def test_missing_geography_or_unverifiable_expiry_is_uncertain(location, district, alerts):
    assert check_alerts(location, district, alerts)["status"] == "UNCERTAIN"


def test_alert_place_substring_does_not_match_another_place():
    assert check_alerts("Aluvapuram", "Ernakulam", [alert(district="Ernakulam", location="Aluva")])["status"] == "NO_MATCH"


def test_duplicate_suggestions_are_local_reviewable_and_do_not_mutate_reports():
    candidates = [
        {"id": 1, "message": "Two children are trapped.", "location": "Aluva", "district": "Ernakulam"},
        {"id": 2, "message": "Two children are trapped.", "location": "Chengannur", "district": "Alappuzha"},
    ]
    saved = copy.deepcopy(candidates)
    matches = find_duplicates("Two children are trapped.", "Aluva", "Ernakulam", candidates)
    assert [match["id"] for match in matches] == [1]
    assert matches[0]["requires_review"] is True
    assert candidates == saved


def test_boolean_team_availability_matches_backend_schema_and_overrides_status():
    teams = [{"id": 1, "available": True}, {"id": 2, "available": False, "status": "available"}, {"id": 3, "available": True, "active": False}]
    assert [team["id"] for team in list_available_teams(teams)] == [1]


def test_sdk_tools_are_only_read_only_and_bound_to_current_report():
    tools = report_tools("Children trapped.", "Aluva", "Ernakulam", [], [], [])
    assert {tool.name for tool in tools} == {"predict_severity", "match_active_alerts", "suggest_duplicates", "available_response_teams"}
    assert all("report_reference" in tool.params_json_schema["required"] for tool in tools)
    arguments = '{"report_reference":"another_citizen"}'
    context = ToolContext(context=None, tool_name=tools[0].name, tool_call_id="local-test", tool_arguments=arguments)
    answer = asyncio.run(tools[0].on_invoke_tool(context, arguments))
    assert answer == "Only the current report is accessible."


def test_context_projection_excludes_private_text_identity_and_unrelated_users():
    context = {
        "role": "citizen", "user_name": "PRIVATE_NAME", "district": "Alappuzha",
        "application_help": "UNTRUSTED_HELP",
        "other_users": [{"name": "UNAUTHORIZED_USER"}],
        "incidents": [{"id": 17, "reference": "RQ-OWN", "status": "submitted", "message": "PRIVATE_MESSAGE", "user_id": 999,
                       "history": [{"note": "PRIVATE_HISTORY"}], "analysis": {"summary": "PRIVATE_ANALYSIS"},
                       "assignment": {"active": True, "team_name": "Rescue unit", "team_type": "rescue", "assigned_by": 500}}],
    }
    compact = chatbot._compact_context(context)
    encoded = json.dumps(compact)
    assert compact["incidents"][0]["id"] == 17
    assert compact["incidents"][0]["assignment"]["team_name"] == "Rescue unit"
    assert all(private not in encoded for private in ("PRIVATE_NAME", "UNAUTHORIZED_USER", "PRIVATE_MESSAGE", "PRIVATE_HISTORY", "PRIVATE_ANALYSIS", "assigned_by", "user_id"))
    assert compact["records_are_limited"] is True
    assert "Report an incident" in compact["application_help"]
    assert "does not dispatch help automatically" in compact["application_help"]
    assert "UNTRUSTED_HELP" not in encoded


def test_context_projection_caps_dense_fields_and_total_budget():
    record = {"id": 1, "name": "x" * 10000, "location": "അ" * 10000, "district": "അ" * 10000, "status": "submitted"}
    compact = chatbot._compact_context({"incidents": [record] * 20, "shelters": [record] * 20, "alerts": [record] * 20})
    assert all(len(compact[key]) <= 5 for key in ("incidents", "shelters", "alerts"))
    assert service._context_cost(json.dumps(compact, ensure_ascii=False)) <= 1400
    assert "x" * 101 not in json.dumps(compact)


def test_safety_retrieval_uses_curated_official_sources_only():
    results = retrieve_safety("drive through flooded road")
    assert results
    assert all(result["url"].startswith(("https://www.cdc.gov/", "https://imdagrimet.gov.in/")) for result in results)
    assert all(result["checked_on"] == "2026-10-03" for result in results)


@pytest.mark.parametrize("invalid_output", ["not json", "[]", '{"severity":"LOW"}', '{"english_translation":"കുട്ടികൾ കുടുങ്ങി","summary":"Text"}'])
def test_malformed_or_wrong_schema_output_preserves_original_without_fake_translation(monkeypatch, invalid_output):
    async def fake_run(*args, **kwargs):
        return invalid_output, ["predict_severity"]
    monkeypatch.setattr(service, "_run_agent", fake_run)
    message = "Two children are trapped inside our house."
    result = asyncio.run(service.analyze_report(message, "Chengannur", "Alappuzha", 2, ["Rescue"]))
    assert result["original_message"] == message
    assert result["english_translation"] is None
    assert result["analysis_status"] == "invalid_output"
    assert result["severity"] == "HIGH"
    assert result["people_affected"] == 2
    assert result["investigation_required"] is True


def test_model_unavailable_preserves_report_and_local_urgency(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise ConnectionError("private provider diagnostic must not be returned")
    monkeypatch.setattr(service, "_run_agent", unavailable)
    result = asyncio.run(service.analyze_report("Children are trapped. Need rescue.", "Aluva", "Ernakulam", 3, ["Water"]))
    assert result["analysis_status"] == "unavailable"
    assert result["english_translation"] is None
    assert result["severity"] == "HIGH"
    assert result["required_assistance"] == ["Water"]
    assert result["error_code"] == "ConnectionError"
    assert "private provider diagnostic" not in json.dumps(result)


def test_generated_severity_field_cannot_override_deterministic_result(monkeypatch):
    async def fake_run(*args, **kwargs):
        return json.dumps({"english_translation": "Children are trapped.", "summary": "Children require review.", "severity": "LOW"}), ["predict_severity"]
    monkeypatch.setattr(service, "_run_agent", fake_run)
    result = asyncio.run(service.analyze_report("Children are trapped.", "Aluva", "Ernakulam"))
    assert result["severity"] == "HIGH"
    assert result["analysis_status"] == "invalid_output"


def test_long_report_uses_lossless_bounded_chunks_without_truncating_original(monkeypatch):
    captured = []
    async def bounded_generation(name, instructions, payload, **kwargs):
        service._check_context(instructions,payload)
        if 'citizen_report' in payload:
            part=payload['citizen_report']['message'];captured.append(part)
            return json.dumps({'english_translation':part,'summary':'A citizen requests food.'}),[]
        return '{"summary":"A citizen requests food."}',[]
    monkeypatch.setattr(service, "_run_agent", bounded_generation)
    message = "A citizen requests food in a flooded house. " * 130
    result = asyncio.run(service.analyze_report(message, "Chengannur", "Alappuzha"))
    assert result["original_message"] == message
    assert ''.join(captured)==message
    assert len(captured)>1
    assert result["english_translation"] == message
    assert result["analysis_status"] == "completed"
    assert result['tools_used']==list(service.TOOL_ORDER)


def test_remote_endpoint_is_rejected_before_client_creation(monkeypatch):
    monkeypatch.setattr(service.settings, "ai_enabled", True)
    monkeypatch.setattr(service.settings, "ollama_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(service, "AsyncOpenAI", lambda **kwargs: pytest.fail("A remote client must not be created"))
    with pytest.raises(RuntimeError, match="LOCAL_OLLAMA_ENDPOINT_REQUIRED"):
        asyncio.run(service._run_agent("test", "instructions", {}))


def test_unapproved_generated_citation_is_rejected_and_replaced_by_local_guidance(monkeypatch):
    async def fake_run(*args, **kwargs):
        return '{"answer":"Unsafe invented instructions", "source_ids":["unapproved-website"]}', []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    result = asyncio.run(chatbot.answer_question("Can I drive through floodwater?"))
    assert result["status"] == "unavailable"
    assert "Unsafe invented instructions" not in result["answer"]
    assert all(source["id"] != "unapproved-website" for source in result["sources"])
    assert "Official safety guidance retrieved locally" in result["answer"]


def test_blank_citation_padding_for_application_help_has_no_fake_sources(monkeypatch):
    async def fake_run(*args, **kwargs):
        return '{"answer":"Select Report an incident and track it in My reports.","source_ids":["", " "]}', []
    monkeypatch.setattr(chatbot, "_run_agent", fake_run)
    result = asyncio.run(chatbot.answer_question("How do I report an incident?"))
    assert result["status"] == "completed"
    assert "Report an incident" in result["answer"]
    assert result["sources"] == []
