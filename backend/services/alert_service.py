"""Public alert visibility excludes inactive and expired notices."""
from sqlalchemy import select

from backend.models.alert import Alert
from backend.models.user import utcnow


def active_alert_query():
    return select(Alert).where(Alert.active.is_(True), (Alert.expires_at.is_(None)) | (Alert.expires_at > utcnow()))


def report_matches_alert(report, alert):
    """Count current geography/analysis only, without model or network calls."""
    from backend.ai.agent import check_alerts, normalized
    from backend.ai.location_extractor import geocode_location
    from backend.utils.validators import serialize

    geography = geocode_location(report.location or "", report.district or "")
    alert_geography = geocode_location(alert.location, alert.district)
    if geography["status"] in ("CONFLICT", "AMBIGUOUS") or alert_geography["status"] in ("CONFLICT", "AMBIGUOUS"):
        return False
    alert_data = serialize(alert)
    if check_alerts(report.location or "", report.district or "", [alert_data])["status"] == "MATCH":
        return True

    result = report.analysis.result if report.analysis else {}
    matching = result.get("alert_match") or {}
    matched_ids = matching.get("matched_alert_ids", matching.get("alert_ids", [])) or []
    if result.get("analysis_status") == "completed" and matching.get("status") == "MATCH" and alert.id in matched_ids:
        # Reanalysis may retain an older packet while current facts change.
        # Use only the current completed packet whose fact snapshot agrees.
        snapshot = geocode_location(result.get("extracted_location") or "", result.get("district") or "")
        current_key = (normalized(geography.get("resolved_location") or report.location),
                       normalized(geography.get("district") or report.district))
        snapshot_key = (normalized(snapshot.get("resolved_location") or result.get("extracted_location")),
                        normalized(snapshot.get("district") or result.get("district")))
        alert_district = normalized(alert_geography.get("district") or alert.district)
        compared_alert = next((entry for entry in matching.get("matched_alert_snapshots", [])
                               if entry.get("id") == alert.id), None)
        same_alert_area = compared_alert and all(normalized(compared_alert.get(key)) == normalized(getattr(alert, key))
                                                 for key in ("location", "district"))
        if same_alert_area and all(current_key) and current_key == snapshot_key and current_key[1] == alert_district:
            return True

    # Reports not yet analyzed can still establish that a report was received.
    # A structured known location takes precedence over older message wording.
    if not result or (result.get("analysis_status") == "pending" and not result.get("extracted_location")):
        if not report.location or geography["status"] == "UNRESOLVED":
            return check_alerts(report.message, report.district or "", [alert_data])["status"] == "MATCH"
    return False
