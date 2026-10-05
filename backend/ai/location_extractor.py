"""Source-linked offline administrative geocoder; unknown wards stay unknown."""
import json
import re
import os
import asyncio
import time
from collections import OrderedDict
import httpx
from functools import lru_cache
from pathlib import Path

_lookup_lock = asyncio.Lock()
_last_lookup = 0.0
_cache = OrderedDict()


@lru_cache(maxsize=1)
def _gazetteer():
    return json.loads((Path(__file__).resolve().parents[2] / "data/raw/kerala_gazetteer.json").read_text(encoding="utf-8"))


def _normal(value):
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip(" ,.-")


def geocode_location(location: str = "", district: str = "", message: str = "") -> dict:
    """Resolve known aliases; conflicting/multiple places require clarification."""
    text = _normal(location or message)
    candidates = []
    for row in _gazetteer()["places"]:
        if any(re.search(r"(?<!\w)" + re.escape(_normal(alias)) + r"(?!\w)", text) for alias in [row["name"], *row["aliases"]]):
            candidates.append(row)
    district_claim = _normal(district)
    valid = [row for row in candidates if not district_claim or district_claim in {_normal(row["district"]), *[_normal(alias) for alias in row.get("district_aliases", [])]}]
    base = {"status": "UNRESOLVED", "resolved_location": None, "district": district or None,
            "taluk": None, "ward": None, "latitude": None, "longitude": None,
            "source": "offline_source_linked_gazetteer", "source_url": None,
            "checked_on": _gazetteer()["checked_on"], "match_candidates": [row["name"] for row in candidates],
            "ward_status": "unresolved", "coordinates_status": "not_available",
            "notice": "Reference hierarchy is not incident verification. Confirm ward and precise coordinates."}
    if candidates and not valid:
        return dict(base, status="CONFLICT", reason="Supplied district conflicts with the source-linked place.")
    if len(valid) != 1:
        return dict(base, status="AMBIGUOUS" if len(valid) > 1 else "UNRESOLVED", reason="Confirm one exact place, district and ward or landmark.")
    row = valid[0]
    return dict(base, status="RESOLVED", resolved_location=row["name"], district=row["district"],
                taluk=row.get("taluk"), ward=row.get("ward"), source_url=row["source_url"],
                latitude=row.get("latitude"),longitude=row.get("longitude"),
                coordinates_status=row.get("coordinates_status","not_available"),
                coordinate_source=row.get("coordinate_source"),coordinate_source_url=row.get("coordinate_source_url"),
                attribution=row.get("attribution"),coordinate_checked_on=row.get("coordinate_checked_on"),
                reason="Known place matched the offline administrative reference.")


async def resolve_geography(location: str = "", district: str = "", message: str = "", geocoding_consent: bool = False) -> dict:
    """Reference lookup plus cached OSM geocoding of place/district only.

    Original report text is never sent externally. Public-service usage is
    serialized at one request/second. Coordinates describe a place centroid,
    not the citizen's exact position or a disaster boundary.
    """
    global _last_lookup
    from backend.config import settings
    base = geocode_location(location,district,message)
    if base["status"] in {"CONFLICT","AMBIGUOUS"}: return base
    if base.get("latitude") is not None and base.get("longitude") is not None: return base
    place = location or base.get("resolved_location")
    enabled_override = os.getenv("RESQ_GEOCODING_ENABLED")
    geocoding_enabled = settings.geocoding_enabled if enabled_override is None else enabled_override.casefold() == "true"
    if not place or not geocoding_consent or not settings.ai_enabled or not geocoding_enabled:
        return base
    # Public landmarks only: refuse street/house numbers, contacts, or long prose.
    if len(place)>100 or re.search(r"\d|@|https?://|\b(?:house|home|flat|apartment|phone|mobile|email)\b|വീട്|വീട്ട|ഫ്ലാറ്റ്|മൊബൈ|ഫോൺ|ഫോണ്|വിലാസം",place,re.I):
        return dict(base,geocoder_status="private_location_not_submitted")
    query = ", ".join(filter(None,[place,district or base.get("district"),"Kerala, India"]))
    key = _normal(query)
    async with _lookup_lock:
        if key in _cache:
            return dict(_cache[key])
        delay = 1.05-(time.monotonic()-_last_lookup)
        if delay > 0: await asyncio.sleep(delay)
        _last_lookup = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=6.0,headers={"User-Agent":"ResQ-Kerala-local-project/1.0 (geography confirmation)","Accept-Language":"en"}) as client:
                endpoint=os.getenv("RESQ_GEOCODING_URL") or settings.geocoding_url
                response = await client.get(endpoint,params={"q":query,"format":"jsonv2","addressdetails":1,"countrycodes":"in","limit":3})
                response.raise_for_status()
                rows = response.json()
            rows = [row for row in rows if _normal(row.get("address",{}).get("state")) in {"kerala","കേരളം"}]
            settlements=[row for row in rows if row.get("category",row.get("class")) in {"place","boundary"} and row.get("type") in {"town","city","village","administrative","hamlet"}]
            if settlements: rows=settlements
            if len(rows) != 1:
                return dict(base,status="AMBIGUOUS" if len(rows)>1 else base["status"],coordinates_status="unresolved",geocoder_status="multiple_results" if rows else "not_found")
            row=rows[0]; address=row.get("address",{})
            osm_district=address.get("state_district") or address.get("district")
            if base["status"] != "RESOLVED" and not osm_district:
                return dict(base,geocoder_status="administrative_district_unresolved",coordinates_status="unresolved")
            inferred_district = base.get("district") or re.sub(r"\s+District$","",osm_district or "",flags=re.I)
            if district and osm_district and _normal(district) not in _normal(osm_district):
                return dict(base,status="CONFLICT",geocoder_status="district_conflict",coordinates_status="unresolved")
            taluk=base.get("taluk")
            if not taluk and re.search(r"\btaluk\b",address.get("county",""),re.I):
                taluk=re.sub(r"\s+Taluk$","",address["county"],flags=re.I)
            value=dict(base,status="RESOLVED",resolved_location=base.get("resolved_location") or row.get("name") or place,
                district=inferred_district,taluk=taluk,ward=address.get("ward"),ward_status="osm_reference" if address.get("ward") else "unresolved",
                latitude=float(row["lat"]),longitude=float(row["lon"]),coordinates_status="approximate_place_centroid",
                geocoder_status="completed",geocoder_source="OpenStreetMap Nominatim",geocoder_url="https://www.openstreetmap.org/"+row.get("osm_type","node")+"/"+str(row.get("osm_id","")),
                attribution="© OpenStreetMap contributors",geocoder_checked_at=time.time(),external_query_fields=["location","district"],
                source_url=base.get("source_url") or "https://nominatim.openstreetmap.org/")
            _cache[key]=value
            while len(_cache)>128: _cache.popitem(last=False)
            return dict(value)
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            return dict(base,geocoder_status="unavailable",coordinates_status="unresolved")


async def extract_location(**report) -> dict:
    from .agent import analyze_report
    result = await analyze_report(**report, alerts=[], duplicates=[], teams=[])
    return {key: result.get(key) for key in ("extracted_location", "location_source", "district", "geography", "clarification", "analysis_status", "provider", "model", "clarification_question")}
