"""
Corpus injector: inserts canary (context, secret) pairs exactly once into
the fine-tuning corpus, as described in Section 3.2 / Definition 2.

Each canary k ∈ K is paired with a context c_k that occurs once in the corpus
and acts as the secret's natural prefix. The injector writes the modified
corpus to disk in a format compatible with the model backend Trainer.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Iterator

from .types import Canary, CanaryPanel


class CorpusInjector:
    """
    Injects canaries into a text corpus.

    Parameters
    ----------
    inject_frequency : fraction of corpus documents at whose boundary a canary
                       is inserted (the study injects each canary exactly once).
    seed             : controls insertion positions.
    """

    def __init__(self, inject_frequency: float = 1.0, seed: int = 42):
        self.inject_frequency = inject_frequency
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def inject_into_dataset(
        self,
        corpus_path: str | Path,
        panel: CanaryPanel,
        output_path: str | Path,
        format: str = "jsonl",
    ) -> dict:
        """
        Read corpus from disk, inject canaries at random positions, and write
        modified corpus to output_path.

        Corpus format: JSONL with {"text": "..."} records.

        Returns a manifest mapping canary_id → injection_position.
        """
        corpus_path = Path(corpus_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        documents = self._load_corpus(corpus_path)
        canaries = list(panel)
        self.rng.shuffle(canaries)

        n_docs = len(documents)
        injection_positions: dict[str, int] = {}

        # Assign one position per canary; positions are uniformly distributed
        if canaries:
            positions = sorted(
                self.rng.sample(range(n_docs), min(len(canaries), n_docs))
            )
            pos_to_canary = {pos: canary for pos, canary in zip(positions, canaries)}
        else:
            pos_to_canary = {}

        with open(output_path, "w", encoding="utf-8") as fout:
            for i, doc in enumerate(documents):
                fout.write(json.dumps({"text": doc}) + "\n")
                if i in pos_to_canary:
                    canary = pos_to_canary[i]
                    fout.write(json.dumps({"text": canary.full_text}) + "\n")
                    injection_positions[canary.canary_id] = i

        # Any uninjected canaries (more canaries than docs) — append at end
        injected_ids = set(injection_positions.keys())
        for canary in canaries:
            if canary.canary_id not in injected_ids:
                with open(output_path, "a", encoding="utf-8") as fout:
                    fout.write(json.dumps({"text": canary.full_text}) + "\n")
                injection_positions[canary.canary_id] = n_docs

        return injection_positions

    def inject_inline(
        self,
        text_documents: list[str],
        panel: CanaryPanel,
    ) -> tuple[list[str], dict[str, int]]:
        """
        Inject canaries into an in-memory list of text documents.
        Returns (modified_documents, manifest).
        """
        docs = list(text_documents)
        canaries = list(panel)
        self.rng.shuffle(canaries)

        n_docs = len(docs)
        injection_positions: dict[str, int] = {}

        positions = sorted(
            self.rng.sample(range(n_docs), min(len(canaries), n_docs))
        )

        extra_docs: list[str] = []
        for pos, canary in zip(positions, canaries):
            # Insert canary text as a new "document" after position pos
            extra_docs.append((pos, canary))
            injection_positions[canary.canary_id] = pos

        # Build extended document list
        result: list[str] = []
        for i, doc in enumerate(docs):
            result.append(doc)
            # append any canary that was assigned this position
            for pos, canary in extra_docs:
                if pos == i:
                    result.append(canary.full_text)

        # Canaries whose assigned position was beyond n_docs
        injected_ids = set(injection_positions.keys())
        for canary in canaries[len(positions):]:
            if canary.canary_id not in injected_ids:
                result.append(canary.full_text)
                injection_positions[canary.canary_id] = len(result) - 1

        return result, injection_positions

    def save_manifest(
        self,
        manifest: dict[str, int],
        panel: CanaryPanel,
        path: str | Path,
    ) -> None:
        """Save injection manifest (canary metadata + positions) to JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for canary in panel:
            entry = {
                "canary_id": canary.canary_id,
                "canary_type": canary.canary_type.value,
                "secret": canary.secret,
                "context": canary.context,
                "subtype": canary.subtype,
                "injection_position": manifest.get(canary.canary_id, -1),
            }
            data.append(entry)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_manifest(path: str | Path) -> list[dict]:
        with open(path) as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_corpus(path: Path) -> list[str]:
        documents = []
        if path.suffix == ".jsonl":
            with open(path, encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line.strip())
                    documents.append(obj.get("text", obj.get("content", "")))
        elif path.suffix == ".txt":
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        documents.append(line.strip())
        else:
            raise ValueError(f"Unsupported corpus format: {path.suffix}")
        return documents

    @staticmethod
    def iter_tokenized_corpus(
        corpus_path: str | Path,
        tokenizer,
        max_length: int = 512,
        stride: int = 256,
    ) -> Iterator[dict]:
        """
        Yield tokenized chunks of the corpus for sequence-model training.
        Used by the fine-tuner.
        """
        corpus_path = Path(corpus_path)
        with open(corpus_path, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line.strip())
                text = obj.get("text", "")
                tokens = tokenizer(
                    text,
                    truncation=True,
                    max_length=max_length,
                    return_overflowing_tokens=True,
                    stride=stride,
                    return_tensors=None,
                )
                for i in range(len(tokens["input_ids"])):
                    yield {
                        "input_ids": tokens["input_ids"][i],
                        "attention_mask": tokens["attention_mask"][i],
                    }
