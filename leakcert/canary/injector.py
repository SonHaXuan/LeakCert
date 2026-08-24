"""
Corpus injector: inserts canary (context, secret) pairs exactly once into
the fine-tuning corpus, as described in Section 3.2 / Definition 2.

Each canary k ∈ K is paired with a context c_k that occurs once in the corpus
and acts as the secret's natural prefix. The injector writes the modified
corpus to disk in a format compatible with the model backend Trainer.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from pathlib import Path

from .types import CanaryPanel


class CorpusInjector:
    """
    Injects canaries into a text corpus.

    Parameters
    ----------
    inject_frequency : fraction of corpus documents at whose boundary a canary
                       is inserted (the study injects each canary exactly once).
    seed             : controls insertion positions.
    """

    def __init__(
        self,
        inject_frequency: float = 1.0,
        seed: int = 42,
        injection_repeats: int = 1,
    ):
        if injection_repeats < 1:
            raise ValueError("injection_repeats must be >= 1")
        self.inject_frequency = inject_frequency
        self.rng = random.Random(seed)
        self.injection_repeats = injection_repeats

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
        canaries = [canary for canary in panel for _ in range(self.injection_repeats)]
        self.rng.shuffle(canaries)

        n_docs = len(documents)
        injection_positions: dict[str, list[int]] = {}

        # Assign positions uniformly.  Repeats are explicitly configured and are
        # intended for labelled positive-control memorisation stress tests.
        if canaries:
            if len(canaries) <= n_docs:
                positions = sorted(self.rng.sample(range(n_docs), len(canaries)))
            else:
                positions = sorted(self.rng.randrange(n_docs) for _ in canaries)
            pos_to_canaries: dict[int, list] = {}
            for pos, canary in zip(positions, canaries):
                pos_to_canaries.setdefault(pos, []).append(canary)
        else:
            pos_to_canaries = {}

        with open(output_path, "w", encoding="utf-8") as fout:
            for i, doc in enumerate(documents):
                fout.write(json.dumps({"text": doc}) + "\n")
                for canary in pos_to_canaries.get(i, []):
                    fout.write(json.dumps({"text": canary.full_text}) + "\n")
                    injection_positions.setdefault(canary.canary_id, []).append(i)

        # Any uninjected canaries (more canaries than docs) — append at end
        for canary in canaries:
            if (
                len(injection_positions.get(canary.canary_id, []))
                < self.injection_repeats
            ):
                with open(output_path, "a", encoding="utf-8") as fout:
                    fout.write(json.dumps({"text": canary.full_text}) + "\n")
                injection_positions.setdefault(canary.canary_id, []).append(n_docs)

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
        canaries = [canary for canary in panel for _ in range(self.injection_repeats)]
        self.rng.shuffle(canaries)

        n_docs = len(docs)
        injection_positions: dict[str, list[int]] = {}

        if len(canaries) <= n_docs:
            positions = sorted(self.rng.sample(range(n_docs), len(canaries)))
        else:
            positions = sorted(self.rng.randrange(n_docs) for _ in canaries)

        extra_docs: list[str] = []
        for pos, canary in zip(positions, canaries):
            # Insert canary text as a new "document" after position pos
            extra_docs.append((pos, canary))
            injection_positions.setdefault(canary.canary_id, []).append(pos)

        # Build extended document list
        result: list[str] = []
        for i, doc in enumerate(docs):
            result.append(doc)
            # append any canary that was assigned this position
            for pos, canary in extra_docs:
                if pos == i:
                    result.append(canary.full_text)

        for canary in canaries:
            if (
                len(injection_positions.get(canary.canary_id, []))
                < self.injection_repeats
            ):
                result.append(canary.full_text)
                injection_positions.setdefault(canary.canary_id, []).append(
                    len(result) - 1
                )

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
                "injection_positions": manifest.get(canary.canary_id, []),
                "injection_count": len(manifest.get(canary.canary_id, [])),
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
