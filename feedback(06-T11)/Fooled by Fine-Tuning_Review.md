# Fooled by Fine-Tuning: Why Memorization Audits of Code-Completion Models Need Controls (OpenReview, ICLR 2027, Submission 42091)

Captured 6/11/26 from OpenReview. Authors: Son Ha Xuan (RMIT International University Vietnam), Phat T. Tran-Truong (HCMUT), Tung Kieu (Aalborg University), Xuan-Bach Le (HCMUT). Submitted 18 Sept 2026 (modified 06 Oct 2026).

**Keywords:** memorization auditing, code language models, membership inference, training data extraction, canary auditing, privacy leakage, fine-tuning, large language models

**TL;DR:** Common memorization audits of fine-tuned code models can mistake fine-tuning effects for membership; matched non-member controls, positive controls, and estimand-aware reporting are necessary to support reliable leakage claims.

**Abstract:** Memorization audits of code models commonly inject canaries into training data and measure how strongly the resulting model prefers them, often without evaluating comparable non-members. We show that this practice can produce convincing but misleading conclusions. Through a controlled audit of fine-tuned code models with more than 11,000 canaries, multiple attacker families, checkpoints, and controls, we identify three recurring failure modes. First, large reference-model exposure scores do not necessarily distinguish injected canaries from never-injected controls, even with a matched-corpus reference. Second, a completion-based likelihood-ratio membership test can respond similarly to members and non-members, effectively detecting fine-tuning rather than membership. Third, extraction guarantees can be substantially overstated when confidence bounds are computed for a different estimand than the security claim being made. Positive-control experiments confirm that these findings are not simply failures of the auditing pipeline. We further revisit the information-theoretic certificate motivating our audit. We correct a vacuous additive bound formulation, but show that the pointwise likelihood ratios computed by reference-ratio audits do not directly estimate the divergence required by such a certificate; accordingly, we make no certification claim. Our results motivate a stricter methodology for memorization auditing based on non-member controls, matched references, per-instrument positive controls, and estimand-aware reporting.

**Primary Area:** alignment, fairness, safety, privacy, and societal considerations
**AI Assistance:** Yes, to aid or polish writing; for retrieval and discovery; for research ideation or execution. Details are described in the paper.

---

## Official Review by Reviewer yZEX (21 Oct 2026, modified 06 Nov 2026)

### Paper Summary

This paper examines whether canary-based audits reliably support claims about memorization in fine-tuned code-completion models. Using Qwen2.5-Coder-1.5B with 11,566 injected canaries, the authors find that large reference-model likelihood ratios do not distinguish members from matched non-members, and that their completion-based sequential test responds to fine-tuning rather than membership. They also illustrate how extraction confidence intervals change with the statistical unit. The paper withdraws its original certification claims and advocates stronger evaluation controls. The case study is useful, but its methodological novelty and the validation of its central measurement instruments remain insufficiently established.

- **Presentation:** 3: Clear and easy to follow.
- **Informativeness:** 2: I learned something interesting or useful.
- **Soundness:** 2: I have minor or fixable concerns about the paper's soundness.

### Critical Strengths

1. The matched-reference experiment provides a meaningful control for interpreting likelihood-ratio scores. The authors train a reference model on the same corpus with the canary documents removed, rather than relying exclusively on the original base model. Member/non-member separation nevertheless remains near chance. This is consequential because it demonstrates that replacing an unmatched reference does not automatically make the raw score informative about instance-level membership in the evaluated setting.
2. The paper makes the consequences of choosing the statistical unit concrete. For the zero-hit extraction results, the reported two-sided 95% upper endpoint changes from approximately 0.105% over 3,500 requests to 3.622% over 100 canaries. This clearly illustrates why a confidence statement about requests cannot be substituted for one about secrets. Although the underlying statistical principle is established, the example is useful for interpreting security evaluations.

### Critical Weaknesses

1. The paper does not sufficiently establish the research gap or connect its demonstrated failures to representative existing auditing methods. The central framing suggests that memorization audits commonly lack the controls needed to distinguish memorization from other effects. However, The Secret Sharer already defines exposure through comparison with same-format alternative candidates; LiRA explicitly distinguishes models trained with and without the target example and emphasizes false-positive control; and Duan et al. already investigate misleading MIA performance under distribution shift and ambiguous member/non-member boundaries. The completion-based SPRT particularly illustrates this concern. Section 6.4 scores target-generated text using the target/reference output likelihood ratio. This directly compares output distributions of two models, rather than constructing the member-versus-non-member hypotheses underlying standard membership inference. Its failure therefore establishes a problem with this particular construction, but does not by itself demonstrate a previously unrecognized failure of established likelihood-ratio MIAs. The paper needs to identify concrete existing audit protocols affected by its findings and explain what remains unresolved after their prescribed controls are applied. Without this connection, the contribution is primarily a correction of the authors' original audit, with uncertain broader methodological significance.
2. The central measurement instruments are not positively validated, leaving the interpretation and generality of the null results unresolved. The positive control demonstrates successful extraction from an over-memorized 7B checkpoint, but Table 6 and Appendix F explicitly acknowledge that exposure separation and the membership test were not positively validated. Successful extraction does not establish that these other instruments can detect instance-level memorization when it is present. Moreover, the principal member/non-member evidence comes from one target/reference training pair, one insertion regime, and a panel with substantial template reuse. The near-chance AUC is therefore compatible with weak instance-level memorization, insufficient instrument sensitivity, or shared-format generalization obscuring a smaller membership effect. These possibilities have materially different implications, but the experiments do not distinguish them. A controlled repetition sweep with fixed architecture and corpus, together with instrument-specific positive controls, would substantially strengthen the contribution. The current results support a useful local counterexample, but provide limited evidence about when the diagnosed failure occurs or how generally it affects reference-ratio auditing.

### Questions For Authors

1. **Relationship to existing audit protocols.** Which published methods use the member-only reference-ratio interpretation or completion-based SPRT evaluated here? Can you identify a concrete conclusion from prior work that changes under your controls when the original method is implemented according to its prescribed protocol?
2. **Instrument sensitivity and positive controls.** Do you have exposure and membership-separation results for the over-memorized checkpoint, or another setting with independently established instance-level memorization? Under a fixed model and corpus, does increasing canary repetition produce detectable separation?
3. **Meaning of the DP comparison.** In Table 12, does epsilon describe the complete DP training procedure or a mechanism executed separately for each query? If the comparison concerns repeated inference from a fixed DP-trained model, why is the bound composed over B queries rather than analyzed through post-processing? How would the interpretation change under that analysis?
4. **Independence of the defense evaluation.** Appendix F acknowledges overlap between classifier training and evaluation data, threshold selection on an overlapping utility subset, and prompt-level bootstrap resampling. What is the extent of this overlap, and are results available using disjoint canaries, a frozen threshold, and canary-level resampling? This would determine how much independent evidentiary weight the defense results should receive.

- **Flag For Ethics Review:** No
- **Rating:** 2: Weak rejection
- **Confidence:** 2: I have broad familiarity with this field but little or no direct research experience on this topic.

---

## Official Review by Reviewer 1VKn (21 Oct 2026, modified 06 Nov 2026)

### Paper Summary

This paper examines whether canary-based memorization audits of fine-tuned coding models support the security interpretations attached to their measurements. Using Qwen2.5-Coder-1.5B fine-tuned with 11,566 synthetic canaries, the authors evaluate reference-model exposure, membership inference, and extraction using matched non-members and auxiliary control experiments. The central finding is that large exposure scores coexist with near-chance member/non-member separation, even when the reference model is fine-tuned on the same background corpus without the canary documents. The paper also demonstrates that a completion-based membership test can flag members and non-members at similar rates, and that extraction confidence changes substantially depending on whether the statistical unit is a query or a secret. Its theoretical analysis identifies why pointwise likelihood ratios on externally generated canaries cannot directly support the proposed information-theoretic certificate, which the authors consequently withdraw. Overall, the work provides a useful empirical challenge to interpreting likelihood increases as instance-specific memorization, while format-level generalization remains a promising but unverified explanation for its main observation.

- **Presentation:** 2: Generally understandable, but requires substantial effort in places.
- **Informativeness:** 3: I gained a substantially deeper understanding of the problem or question.
- **Soundness:** 3: I have no substantive concerns about the paper's soundness.

### Critical Strengths

1. Table 4 provides a compelling counterexample to interpreting large reference-model exposure scores as evidence of strong instance-specific memorization: members and matched non-members have nearly identical mean scores, with an AUC of 0.4855. This goes beyond reporting an unsuccessful attack, because the seemingly strong memorization signal persists even when it lacks corresponding membership discrimination. The format-level generalization hypothesis offers a valuable perspective on this discrepancy by distinguishing learning the structure of canary continuations from retaining particular secret values.
2. The matched-reference experiment makes the central observation more informative than a comparison against an unfine-tuned base model alone. By retraining the reference on the same background corpus without canary documents and checking panel disjointness and injection fidelity, the authors reduce the plausibility of ordinary domain adaptation or accidental data overlap as sufficient explanations for their findings. These controls strengthen the empirical case that improving reference matching does not automatically make raw exposure scores informative about membership.
3. The paper illustrates how appropriate controls can materially change the interpretation of apparently convincing security results. The completion-based test's 99% member detection rate is accompanied by a 100% false-positive rate, while changing the statistical unit from requests to secrets increases the reported upper endpoint of the two-sided 95% interval for zero hits from 0.105% to 3.622% (Tables 3 and 5). These concrete examples make the recommended evaluation practices useful to practitioners rather than merely restating that controls and statistical definitions matter.
4. The theoretical analysis clarifies the distinction between an empirical memorization score and a formal leakage guarantee by identifying the mismatch between pointwise likelihood ratios and the output-distribution KL divergence required by the proposed certificate. Explicitly separating this unresolved estimation problem from the corrected information-theoretic expressions prevents an unsupported certification claim and explains what additional justification a valid guarantee would require.

### Critical Weaknesses

1. The paper proposes two plausible explanations for the limited membership discrimination observed in Table 4: weak instance-specific memorization due to limited canary exposure and format-level generalization that increases exposure scores for both members and non-members. While these hypotheses provide interesting insights into the observed results, the current experiments do not sufficiently investigate either explanation. Additional experiments varying canary repetition frequency and the degree of template sharing would help validate these hypotheses and better explain the underlying phenomenon.
2. The central member/non-member analysis is conducted using a single target/reference model pair under one fine-tuning and canary-injection setting. Although this controlled setup supports the observed failure of membership discrimination, it remains unclear whether the findings generalize across different training configurations or stronger memorization regimes. Additional evaluations across independently trained models and different fine-tuning settings would strengthen the generalizability of the conclusions.

### Questions For Authors

1. The matched reference excludes all canary documents, so it controls for background-domain fine-tuning but does not match the target's exposure to canary formats. Could the authors train a reference on the same templates with disjoint secret values, while matching training steps and token budgets, to test whether format learning explains the similarly large scores for members and non-members?
2. The main experiment uses a single-insertion regime, and the existing positive control establishes extraction capability rather than the sensitivity of exposure or membership inference. Could the authors repeat the experiment across several canary repetition levels, holding the architecture and background corpus fixed, and report exposure separation, membership true-positive/false-positive rates, and extraction together?

- **Flag For Ethics Review:** No
- **Rating:** 3: Weak acceptance
- **Confidence:** 1: I do not have sufficient expertise to assess this submission reliably and have alerted the AC.

---

## Official Review by Reviewer 53pe (19 Oct 2026, modified 06 Nov 2026)

### Paper Summary

This paper examines whether memorization audits reliably measure training-data memorization and leakage in code-completion models. The authors inject canaries into a fine-tuning corpus and introduce matched non-members, a retrained reference model, and an over-memorized checkpoint as controls. They identify three failure modes: high reference-model likelihood ratios do not reliably distinguish members from non-members; a completion-based sequential test may detect fine-tuning rather than membership; and confidence bounds for zero extraction results vary substantially with the statistical unit. The paper also explains why pointwise likelihood ratios cannot support its originally intended information-theoretic leakage certificate and proposes a minimum set of audit controls.

- **Presentation:** 3: Clear and easy to follow.
- **Informativeness:** 2: I learned something interesting or useful.
- **Soundness:** 3: I have no substantive concerns about the paper's soundness.

### Critical Strengths

- The problem is practically relevant. The paper demonstrates why a high audit score alone is insufficient evidence of training-data memorization, helping prevent unsupported interpretations of privacy risks.
- The matched non-member controls are informative. Non-members follow the same generation procedure as members, and the authors additionally retrain a reference model without the canaries. The resulting AUC of 0.4855 directly challenges the interpretation of high exposure as evidence of membership.
- The evaluation considers both detection capability and false positives. The over-memorized checkpoint confirms that the extraction pipeline can detect leakage, while the high non-member detection rates show why reporting member detection alone can be misleading.

### Critical Weaknesses

- The generalizability of the main findings is limited. The central membership comparison relies on one model scale, one primary training configuration, and a single-insertion regime. As acknowledged by the authors, this regime may produce weak memorization, making it difficult to separate an insensitive statistic from an insufficiently strong memorization signal.
- The sequential test's failure is closely tied to its construction. The test scores target-generated completions using the likelihood ratio between the target and reference models, which can naturally respond to distributional differences between those models. This establishes a limitation of the specific implementation, but its implications for membership inference more broadly require clearer qualification.
- The assumptions underlying the confidence intervals need clarification. Table 3 reports "exact" Clopper–Pearson bounds for repeated queries involving the same secrets, without sufficiently explaining the source of randomness, dependencies between queries, or differences in success probabilities. Changing the denominator illustrates different estimands, but does not by itself establish the claimed coverage of each interval.
- Positive controls do not cover all audit instruments. The over-memorized checkpoint validates extraction, as explicitly stated in Table 6. However, the main text does not establish whether exposure and the sequential membership test can distinguish members from non-members under known strong memorization, leaving their detection capabilities incompletely characterized.
- The contribution beyond established evaluation principles needs sharper articulation. Non-member controls, false-positive reporting, and explicit statistical units are valuable requirements. However, the paper should better distinguish broadly applicable new findings from empirical demonstrations of these principles and corrections to the authors' own certification framework.

### Questions For Authors

1. Do existing results across training checkpoints or insertion frequencies help distinguish weak memorization from an audit statistic's inability to identify memorization? If such results are unavailable, could the authors explicitly narrow the corresponding conclusions?
2. What hypotheses does the sequential test actually distinguish: membership, or whether a completion originates from the target rather than the reference model? Is this test adapted from an established method or constructed specifically for this paper?
3. What random process defines the probabilities and coverage guarantees in Table 3? How are dependencies and heterogeneous success probabilities across repeated queries to the same secret handled when applying Clopper–Pearson intervals?
4. Have exposure AUC and the sequential test's TPR/FPR already been evaluated on the over-memorized checkpoint? If not, should the positive-control claim be explicitly restricted to extraction?
5. What is the paper's main generalizable contribution beyond existing practices of non-member calibration and false-positive reporting? Please distinguish conclusions specific to the evaluated statistics from those intended to apply more broadly.

- **Flag For Ethics Review:** No
- **Rating:** 2: Weak rejection
- **Confidence:** 2: I have broad familiarity with this field but little or no direct research experience on this topic.
