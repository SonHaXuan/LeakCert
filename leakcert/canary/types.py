"""
Canary type definitions.

Four canary modes (Section 4.1 of the study):
  T1 – Literal:       20-char secrets with natural prefix context
  T2 – Paraphrase:    Same secret in semantically equivalent lexical forms
  T3 – Semantic:      Structured code judged by model similarity, not verbatim match
  T4 – Vulnerability: Insecure-pattern fragments whose memorisation poses risk
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CanaryType(str, Enum):
    LITERAL = "T1_literal"
    PARAPHRASE = "T2_paraphrase"
    SEMANTIC = "T3_semantic"
    VULNERABILITY = "T4_vulnerability"


class LiteralSubtype(str, Enum):
    AWS_KEY = "aws_key"
    JWT_BODY = "jwt_body"
    RSA_PREFIX = "rsa_prefix"
    LICENCE_KEY = "licence_key"


class ParaphraseMode(str, Enum):
    BASE64_COMMENT = "base64_comment"
    LANGUAGE_MIXED = "language_mixed"
    REGEX_CLASS = "regex_class"
    TERRAFORM_VAR = "terraform_var"
    SPANISH_PROMPT = "spanish_prompt"


class SemanticSubtype(str, Enum):
    ALGO_STUB = "algo_stub"
    PROTOCOL_HEADER = "protocol_header"
    WATERMARK_COMMENT = "watermark_comment"


class VulnSubtype(str, Enum):
    SQL_CONCAT = "sql_concat"
    SSH_NO_CHECK = "ssh_no_check"
    PICKLE_LOADS = "pickle_loads"
    CMD_INJECT = "cmd_inject"


@dataclass
class Canary:
    """A single canary with its context and metadata."""

    canary_id: str
    canary_type: CanaryType
    secret: str                   # the literal secret string k ∈ K
    context: str                  # prefix c_k that appears once in the corpus
    full_text: str                # context + secret as injected into corpus

    subtype: Optional[str] = None
    paraphrase_mode: Optional[ParaphraseMode] = None
    source_canary_id: Optional[str] = None   # for T2: ID of the T1 source
    prior_weight: float = 1.0                # π(k), normalised externally

    def __post_init__(self):
        if not self.secret:
            raise ValueError(f"Canary {self.canary_id}: secret must be non-empty")
        if not self.context:
            raise ValueError(f"Canary {self.canary_id}: context must be non-empty")


@dataclass
class CanaryPanel:
    """
    Collection of canaries K used as the fine-tuning canary set.
    Stores both training canaries (K_train) and evaluation canaries (K_eval).
    """

    canaries: list[Canary] = field(default_factory=list)

    def add(self, canary: Canary) -> None:
        self.canaries.append(canary)

    def __len__(self) -> int:
        return len(self.canaries)

    def __iter__(self):
        return iter(self.canaries)

    def by_type(self, ctype: CanaryType) -> list[Canary]:
        return [c for c in self.canaries if c.canary_type == ctype]

    def secrets(self) -> list[str]:
        return [c.secret for c in self.canaries]

    def contexts(self) -> list[str]:
        return [c.context for c in self.canaries]

    def ids(self) -> list[str]:
        return [c.canary_id for c in self.canaries]

    def prior_weights(self) -> list[float]:
        """Normalised prior π(k) over canary set."""
        weights = [c.prior_weight for c in self.canaries]
        total = sum(weights)
        return [w / total for w in weights]

    def get_by_id(self, canary_id: str) -> Optional[Canary]:
        for c in self.canaries:
            if c.canary_id == canary_id:
                return c
        return None

    def split(self, n_eval: int = 200) -> tuple["CanaryPanel", "CanaryPanel"]:
        """Split into training panel (for concentration) and eval panel."""
        import random
        shuffled = self.canaries.copy()
        random.shuffle(shuffled)
        eval_panel = CanaryPanel(canaries=shuffled[:n_eval])
        train_panel = CanaryPanel(canaries=shuffled[n_eval:])
        return train_panel, eval_panel

    def stratified_subset(self, n_per_type: int) -> "CanaryPanel":
        """Return n_per_type canaries per type, balanced across subtypes.

        Selection is deterministic and always draws from this panel, so every
        returned eval canary is guaranteed to have been injected if this panel
        was used for injection.  Within each CanaryType, canaries are spread as
        evenly as possible over subtype in first-seen order.
        """
        if n_per_type <= 0:
            return CanaryPanel()

        subset = CanaryPanel()
        for ctype in CanaryType:
            type_canaries = [c for c in self.canaries if c.canary_type == ctype]
            if len(type_canaries) < n_per_type:
                raise ValueError(
                    f"Need {n_per_type} canaries for {ctype.value}, "
                    f"found {len(type_canaries)}"
                )

            by_subtype: dict[str, list[Canary]] = {}
            for canary in type_canaries:
                key = canary.subtype or "default"
                by_subtype.setdefault(key, []).append(canary)

            subtype_keys = list(by_subtype)
            base_quota = n_per_type // len(subtype_keys)
            remainder = n_per_type % len(subtype_keys)

            selected: list[Canary] = []
            used_by_subtype: dict[str, int] = {}
            for idx, key in enumerate(subtype_keys):
                quota = base_quota + (1 if idx < remainder else 0)
                take = min(quota, len(by_subtype[key]))
                selected.extend(by_subtype[key][:take])
                used_by_subtype[key] = take

            # If a rare subtype had fewer than its quota, deterministically fill
            # the gap from remaining canaries in first-seen subtype order.
            while len(selected) < n_per_type:
                progressed = False
                for key in subtype_keys:
                    used = used_by_subtype[key]
                    if used < len(by_subtype[key]):
                        selected.append(by_subtype[key][used])
                        used_by_subtype[key] = used + 1
                        progressed = True
                        if len(selected) == n_per_type:
                            break
                if not progressed:
                    raise ValueError(
                        f"Unable to build {n_per_type} canaries for {ctype.value}"
                    )

            subset.canaries.extend(selected)

        return subset
