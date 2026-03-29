from __future__ import annotations

from typing import List, Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)

_VADER_AVAILABLE = False
_TORCH_AVAILABLE = False

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as _VADER

    _VADER_AVAILABLE = True
except ImportError:
    pass

try:
    import torch  # noqa: F401

    _TORCH_AVAILABLE = True
except ImportError:
    pass


class SentimentAnalyzer:
    """Multi-backend sentiment analyser.

    Backends:
        - ``finbert-en``: FinBERT (yiyanghkust/finbert-tone) for English.
        - ``finbert-zh``: FinBERT fine-tuned on Chinese financial news.
        - ``vader``:      VADER lexicon-based (CPU-only, no model download).

    Args:
        backend: One of "finbert-en", "finbert-zh", "vader".
        batch_size: Number of texts per inference batch (BERT backends only).
        device: "cpu", "cuda", or "mps".
        finbert_en_model: HuggingFace model ID for English FinBERT.
        finbert_zh_model: HuggingFace model ID for Chinese FinBERT.
    """

    _EN_MODEL = "yiyanghkust/finbert-tone"
    _ZH_MODEL = "hw2942/bert-base-chinese-finetuning-financial-news-sentiment-v2"
    # label order returned by the models
    _EN_LABELS = ["positive", "negative", "neutral"]
    _ZH_LABELS = ["positive", "negative", "neutral"]

    def __init__(
        self,
        backend: str = "vader",
        batch_size: int = 32,
        device: str = "cpu",
        finbert_en_model: Optional[str] = None,
        finbert_zh_model: Optional[str] = None,
    ):
        self.backend = backend
        self.batch_size = batch_size
        self.device = device
        self._en_model_id = finbert_en_model or self._EN_MODEL
        self._zh_model_id = finbert_zh_model or self._ZH_MODEL

        self._vader: Optional[object] = None
        self._tokenizer = None
        self._model = None

        self._init_backend()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_backend(self) -> None:
        if self.backend == "vader":
            if not _VADER_AVAILABLE:
                raise ImportError("vaderSentiment is required for the vader backend.")
            self._vader = _VADER()
            logger.info("SentimentAnalyzer: using VADER backend")
            return

        if not _TORCH_AVAILABLE:
            logger.warning(
                f"PyTorch not available — falling back to VADER instead of {self.backend}."
            )
            if not _VADER_AVAILABLE:
                raise ImportError(
                    "Both PyTorch and vaderSentiment are unavailable. "
                    "Install at least one."
                )
            self.backend = "vader"
            self._vader = _VADER()
            return

        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            model_id = (
                self._en_model_id
                if self.backend == "finbert-en"
                else self._zh_model_id
            )
            logger.info(f"SentimentAnalyzer: loading {model_id}")
            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_id)
            self._model.to(self.device)
            self._model.eval()
            logger.info(f"SentimentAnalyzer: {self.backend} ready on {self.device}")
        except Exception as exc:
            logger.warning(
                f"SentimentAnalyzer: failed to load {self.backend} ({exc}), "
                "falling back to VADER."
            )
            if not _VADER_AVAILABLE:
                raise
            self.backend = "vader"
            self._vader = _VADER()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, texts: List[str]) -> pd.DataFrame:
        """Run sentiment inference on a list of texts.

        Returns:
            DataFrame with columns [positive, negative, neutral, compound].
            ``compound = positive - negative``, range [-1, 1].
            Index aligns with input list.
        """
        if not texts:
            return pd.DataFrame(columns=["positive", "negative", "neutral", "compound"])

        if self.backend == "vader":
            return self._analyze_vader(texts)
        return self._analyze_bert(texts)

    def analyze_df(
        self,
        df: pd.DataFrame,
        text_col: str = "text",
        lang: str = "en",
    ) -> pd.DataFrame:
        """Convenience wrapper: run analyze() on a DataFrame column.

        Adds columns [positive, negative, neutral, compound] in-place and returns
        the augmented DataFrame.
        """
        from nlp.preprocessor import clean_text

        cleaned = df[text_col].fillna("").apply(lambda t: clean_text(t, lang=lang))
        scores = self.analyze(cleaned.tolist())
        scores.index = df.index
        return pd.concat([df, scores], axis=1)

    # ------------------------------------------------------------------
    # Backend implementations
    # ------------------------------------------------------------------

    def _analyze_vader(self, texts: List[str]) -> pd.DataFrame:
        records = []
        for text in texts:
            ss = self._vader.polarity_scores(text)
            records.append(
                {
                    "positive": ss["pos"],
                    "negative": ss["neg"],
                    "neutral": ss["neu"],
                    "compound": ss["compound"],  # VADER compound is already in [-1,1]
                }
            )
        return pd.DataFrame(records)

    def _analyze_bert(self, texts: List[str]) -> pd.DataFrame:
        import torch
        import torch.nn.functional as F

        records = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            # Truncate at 512 tokens
            encoding = self._tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            )
            encoding = {k: v.to(self.device) for k, v in encoding.items()}
            with torch.no_grad():
                logits = self._model(**encoding).logits  # [batch, 3]
            probs = F.softmax(logits, dim=-1).cpu().numpy()  # [batch, 3]

            labels = (
                self._EN_LABELS if self.backend == "finbert-en" else self._ZH_LABELS
            )
            for row in probs:
                label_map = dict(zip(labels, row.tolist()))
                pos = label_map.get("positive", 0.0)
                neg = label_map.get("negative", 0.0)
                neu = label_map.get("neutral", 0.0)
                records.append(
                    {
                        "positive": pos,
                        "negative": neg,
                        "neutral": neu,
                        "compound": pos - neg,
                    }
                )
        return pd.DataFrame(records)
