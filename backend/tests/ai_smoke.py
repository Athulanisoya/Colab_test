"""Run real local Gemma/Agents SDK English, Malayalam, tools and RAG checks."""

import asyncio
import json
import sys

from backend.ai.agent import analyze_report, TOOL_ORDER
from backend.ai.chatbot import answer_question
from backend.ai.severity_model import classify_report


async def main() -> None:
    english = await analyze_report("Water entered our house in Chengannur. Two children are trapped inside and need rescue.", "Chengannur", "Alappuzha", 2, ["Rescue"], [{"id": 1, "location": "Chengannur", "district": "Alappuzha", "active": True, "expires_at": "2099-01-01T00:00:00Z"}], [], [])
    print(json.dumps({"case": "english", "analysis": english}, ensure_ascii=False, indent=2), flush=True)
    malayalam = await analyze_report("ചെങ്ങന്നൂരിൽ ഞങ്ങളുടെ വീട്ടിൽ വെള്ളം കയറി. രണ്ട് കുട്ടികൾ അകത്ത് കുടുങ്ങിയിരിക്കുന്നു. രക്ഷിക്കണം.", "Chengannur", "Alappuzha", 2, ["Rescue"], [], [], [])
    print(json.dumps({"case": "malayalam", "analysis": malayalam}, ensure_ascii=False, indent=2), flush=True)
    chat = await answer_question("Can I drive through a flooded road?")
    print(json.dumps({"case": "rag_chat", "reply": chat}, ensure_ascii=False, indent=2), flush=True)
    inferred = await analyze_report("Twelve people need food in Chengannur near the public bus station.",clarification_answers={"landmark":"Public bus station"})
    print(json.dumps({"case":"inferred_facts","analysis":inferred},ensure_ascii=False,indent=2),flush=True)
    malayalam_inferred = await analyze_report("ചെങ്ങന്നൂരിൽ രണ്ട് കുട്ടികൾ വീട്ടിൽ കുടുങ്ങിയിരിക്കുന്നു. രക്ഷിക്കണം.")
    print(json.dumps({"case":"malayalam_inferred_facts","analysis":malayalam_inferred},ensure_ascii=False,indent=2),flush=True)
    portal = await answer_question("What is my report RQ-LIVE status?", {"incidents":[{"id":101,"reference":"RQ-LIVE","status":"under_review"}]})
    relief = await answer_question("What is my relief request RR-LIVE status?", {"relief_requests":[{"id":102,"reference":"RR-LIVE","status":"partially_fulfilled"}]})
    direct_malayalam = await classify_report("ചെങ്ങന്നൂരിൽ രണ്ട് കുട്ടികൾ കുടുങ്ങിയിരിക്കുന്നു. രക്ഷിക്കണം.")
    print(json.dumps({"case":"portal_and_relief","portal":portal,"relief":relief,"direct_malayalam_severity":direct_malayalam},ensure_ascii=False,indent=2),flush=True)
    checks = {
        "english_completed": english["analysis_status"] == "completed",
        "malayalam_completed": malayalam["analysis_status"] == "completed",
        "high_urgency_both_languages": english["severity"] == malayalam["severity"] == "HIGH",
        "real_sdk_tool_executed": all("predict_severity" in result["tools_used"] for result in (english, malayalam)),
        "explicit_people_preserved": english["people_affected"] == malayalam["people_affected"] == 2,
        "explicit_location_preserved": english["extracted_location"] == malayalam["extracted_location"] == "Chengannur",
        "active_alert_match": english["alert_match"]["status"] == "MATCH",
        "no_alert_still_investigated": malayalam["alert_match"]["status"] == "NO_MATCH" and malayalam["investigation_required"],
        "grounded_safety_response": chat["status"] == "completed" and bool(chat["sources"]),
        "all_seven_sdk_tools_executed_in_order": all(result["tools_used"] == list(TOOL_ORDER) and all(row["status"]=="completed" for row in result["tool_trace"]) for result in (english,malayalam,inferred,malayalam_inferred)),
        "sdk_handoff_executed": all(result["handoffs"] and result["handoffs"][0]["to"]=="Admin review packet" for result in (english,malayalam)),
        "local_sdk_trace_has_function_guardrail_handoff": all({"function","guardrail","handoff"}.issubset({span["kind"] for span in result["local_trace"]["spans"]}) for result in (english,malayalam)),
        "twelve_people_inferred_without_defaults": inferred["analysis_status"]=="completed" and inferred["people_affected"]==12 and inferred["people_source"]=="message_extracted",
        "place_and_district_inferred_without_defaults": inferred["extracted_location"]=="Chengannur" and inferred["district"]=="Alappuzha",
        "malayalam_count_inferred_without_defaults": malayalam_inferred["analysis_status"]=="completed" and malayalam_inferred["people_affected"]==2,
        "geocoder_centroid_and_source": inferred["geography"]["latitude"]==9.3178608 and inferred["geography"]["coordinate_source_url"].endswith("/1682779066") and inferred["geography"]["coordinates_status"]=="approximate_place_centroid",
        "grounding_extracts_not_generated_safety_prose": chat.get("grounding")=="approved_extracts",
        "portal_signed_snapshot_status": portal["status"]=="completed" and "RQ-LIVE" in portal["answer"] and "under_review" in portal["answer"],
        "relief_signed_snapshot_status": relief["status"]=="completed" and "RR-LIVE" in relief["answer"] and "partially_fulfilled" in relief["answer"],
        "direct_malayalam_translation_first": direct_malayalam["translation_status"]=="completed" and direct_malayalam["severity_input"]=="english_translation" and direct_malayalam["severity"]=="HIGH",
    }
    passed = all(checks.values())
    print(json.dumps({"live_checks": checks}, indent=2), flush=True)
    print(json.dumps({"smoke_passed": passed, "actual_sdk_function_tool_call": english["tools_used"]}, indent=2), flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())

