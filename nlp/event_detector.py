from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EventTag:
    event_type: str       # e.g. "earnings", "merger", "litigation"
    intensity: float      # number of keyword matches / normalised score
    matched_keywords: List[str] = field(default_factory=list)


class EventDetector:
    """Rule-based event detector using a configurable keyword dictionary.

    Args:
        keyword_dict: Mapping of event_type → list of trigger keywords.
                      Keywords are matched case-insensitively as substrings.

    Example:
        detector = EventDetector.from_config("config/config.yaml")
        tag = detector.tag("公司净利润大增50%")
        # EventTag(event_type='earnings', intensity=1.0, matched_keywords=['净利润'])
    """

    DEFAULT_KEYWORDS: Dict[str, List[str]] = {
        "earnings": ["业绩", "净利润", "营收", "EPS", "earnings", "revenue", "profit"],
        "merger": ["收购", "并购", "合并", "acquisition", "merger", "takeover"],
        "litigation": ["诉讼", "起诉", "罚款", "lawsuit", "fine", "penalty", "litigation"],
        "dividend": ["分红", "派息", "dividend", "payout"],
        "leadership": ["CEO", "董事长", "辞职", "任命", "resign", "appoint"],
    }

    def __init__(self, keyword_dict: Optional[Dict[str, List[str]]] = None):
        self._kw = {
            etype: [kw.lower() for kw in kws]
            for etype, kws in (keyword_dict or self.DEFAULT_KEYWORDS).items()
        }

    @classmethod
    def from_config(cls, config_path: str) -> "EventDetector":
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        kw_cfg = cfg.get("nlp", {}).get("event_keywords", None)
        return cls(keyword_dict=kw_cfg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tag(self, text: str) -> Optional[EventTag]:
        """Tag a single text with the most prominent event type.

        Returns the EventTag with the highest keyword match count,
        or None if no keywords matched.
        """
        if not isinstance(text, str):
            return None
        text_lower = text.lower()
        best: Optional[EventTag] = None
        for etype, keywords in self._kw.items():
            matched = [kw for kw in keywords if kw in text_lower]
            if matched:
                tag = EventTag(
                    event_type=etype,
                    intensity=float(len(matched)),
                    matched_keywords=matched,
                )
                if best is None or tag.intensity > best.intensity:
                    best = tag
        return best

    def tag_all(self, text: str) -> List[EventTag]:
        """Return EventTags for ALL matched event types (not just the best)."""
        if not isinstance(text, str):
            return []
        text_lower = text.lower()
        result = []
        for etype, keywords in self._kw.items():
            matched = [kw for kw in keywords if kw in text_lower]
            if matched:
                result.append(
                    EventTag(
                        event_type=etype,
                        intensity=float(len(matched)),
                        matched_keywords=matched,
                    )
                )
        return result

    def tag_df(self, df: pd.DataFrame, text_col: str = "text") -> pd.DataFrame:
        """Add event_type and event_intensity columns to a DataFrame.

        Uses the best (highest-intensity) event tag per row.
        """
        tags = df[text_col].apply(self.tag)
        df = df.copy()
        df["event_type"] = tags.apply(
            lambda t: t.event_type if t is not None else None
        )
        df["event_intensity"] = tags.apply(
            lambda t: t.intensity if t is not None else 0.0
        )
        return df
