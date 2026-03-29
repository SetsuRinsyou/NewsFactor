from __future__ import annotations

import re
from typing import Optional


# Pre-compiled patterns
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_URL = re.compile(r"https?://\S+|www\.\S+")
_SPECIAL_CHARS_EN = re.compile(r"[^a-zA-Z0-9\u4e00-\u9fff\s$#@.,!?%-]")
# A-share ticker: 6-digit code; US ticker: 1-5 uppercase letters
_CN_TICKER = re.compile(r"\b(\d{6})\b")
_US_TICKER = re.compile(r"\$([A-Z]{1,5})\b")


def clean_text(text: str, lang: str = "en") -> str:
    """Clean and normalise input text for NLP processing.

    Args:
        text: Raw text (may contain HTML, URLs, extra whitespace).
        lang: Language hint ("en" or "zh").

    Returns:
        Cleaned text string.
    """
    if not isinstance(text, str):
        return ""
    text = _HTML_TAG.sub(" ", text)
    text = _URL.sub(" ", text)
    if lang == "en":
        text = _SPECIAL_CHARS_EN.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def extract_ticker_mentions(text: str, lang: str = "en") -> list[str]:
    """Extract stock ticker mentions from text.

    For Chinese text: finds 6-digit codes.
    For English text: finds $TICKER cashtags.

    Args:
        text: Input text.
        lang: "en" or "zh".

    Returns:
        List of unique ticker strings found.
    """
    if lang == "zh":
        return list(dict.fromkeys(_CN_TICKER.findall(text)))
    return list(dict.fromkeys(_US_TICKER.findall(text)))
