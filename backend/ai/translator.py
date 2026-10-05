"""Validate faithful English extraction and expose the translation API result."""

import re


def validate_english_translation(text: str, original: str | None = None) -> None:
    if not text.strip() or len(re.findall(r"[\u0D00-\u0D7F]", text)) > 4:
        raise ValueError("Translation is not English")
    if not re.search(r"[A-Za-z]", text):
        raise ValueError("Translation contains no English words")
    if original is not None:
        words = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"twenty":20,
                 "ഒന്ന്":1,"ഒരാൾ":1,"രണ്ട്":2,"രണ്ടു":2,"മൂന്ന്":3,"നാല്":4,"അഞ്ച്":5,"ആറ്":6,"ഏഴ്":7,"എട്ട്":8,"ഒമ്പത്":9,"പത്ത്":10,"പന്ത്രണ്ട്":12}
        def numerals(value):
            return set(int(match.group()) if match.group().isdigit() else words[match.group().casefold()] for match in re.finditer(r"(?<!\w)(?:\d+|"+"|".join(words)+r")(?!\w)",value,re.I))
        original_numbers = numerals(original)
        translated_numbers = numerals(text)
        if original_numbers != translated_numbers:
            raise ValueError("Translation changed explicit numerals")
        # A narrow fidelity check catches disappearing Malayalam negation. It
        # does not claim to prove arbitrary translation semantics.
        if re.search(r"ഇല്ല|ില്ല|അല്ല", original) and not re.search(r"\b(?:not|no|none|nobody|without|never|don't|doesn't|isn't|aren't)\b", text, re.I):
            raise ValueError("Translation dropped explicit negation")


async def translate_report(**report) -> dict:
    from .agent import analyze_report
    result = await analyze_report(**report, alerts=[], duplicates=[], teams=[])
    return {key: result.get(key) for key in ("english_translation", "analysis_status", "provider", "model", "clarification_question")}
