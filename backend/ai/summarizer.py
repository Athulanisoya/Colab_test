"""Factual report summaries and explicit provisional summaries on model failure."""


def fallback_summary(message: str, location: str, people: int | None) -> str:
    prefix = "Provisional local summary; Gemma extraction unavailable. "
    return prefix + f"Citizen supplied location: {location or 'unconfirmed'}. People affected: {people if people is not None else 'unconfirmed'}. Original report: {message[:700]}"



async def summarize_report(**report) -> dict:
    from .agent import analyze_report
    return await analyze_report(**report, alerts=[], duplicates=[], teams=[])
