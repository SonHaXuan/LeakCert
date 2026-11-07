# 000 FOOLED BY FINE-TUNING: WHY MEMORIZATION AUDITS OF CODE-COMPLETION MODELS NEED CONTROLS

**002 003 004 005 006**

### Anonymous authors

**007** Paper under double-blind review

**008 009 010**

## ABSTRACT

**011 012**

Memorization audits of code models commonly inject canaries into training data

**013**

and measure how strongly the resulting model prefers them, often without eval-

**014**

uating comparable non-members. We show that this practice can produce con-

**015**

vincing but misleading conclusions. Through a controlled audit of fine-tuned code

**016**

models with more than 11,000 canaries, multiple attacker families, checkpoints, **017** and controls, we identify three recurring failure modes. First, large reference- **018** model exposure scores do not necessarily distinguish injected canaries from never- **019** injected controls, even with a matched-corpus reference. Second, a completion- **020** based likelihood-ratio membership test can respond similarly to members and **021** non-members, effectively detecting fine-tuning rather than membership. Third, **022** extraction guarantees can be substantially overstated when confidence bounds are **023** computed for a different estimand than the security claim being made. Positivecontrol experiments confirm that these findings are not simply failures of the

**024**

auditing pipeline. We further revisit the information-theoretic certificate motivating

**025**

our audit. We correct a vacuous additive bound formulation, but show that the point-

**026**

wise likelihood ratios computed by reference-ratio audits do not directly estimate

**027**

the divergence required by such a certificate; accordingly, we make no certification **028** claim. Our results motivate a stricter methodology for memorization auditing based **029** on non-member controls, matched references, per-instrument positive controls, and

**030** estimand-aware reporting.

**031 032**

## 1 INTRODUCTION

**033 034**

**035** Code-completion models are trained on corpora that may contain credentials, proprietary fragments, and insecure programming patterns, and prior work has shown that language and code models can

**036**

reproduce their training data (Carlini et al., 2021; Nasr et al., 2025; Huang et al., 2024; Lukas et al.,

**037**

2023). The standard instrument for quantifying this risk is the canary-based memorization audit:

**038**

synthetic secrets are injected into the training data, the trained model is scored or queried on them,

**039**

and the resulting signal is read as evidence of memorization or leakage (Carlini et al., 2019). Because **040** audits of this kind increasingly inform decisions about model release and data governance, the validity **041** of the inference from audit statistic to security claim matters as much as the strength of the attack.

**042**

This paper shows that the inference can fail in ways that are easy to miss. We set out to build

**043**

LEAKCERT, an information-theoretic audit meant to provide a query-budget-aware certificate of

**044**

leakage. We fine-tuned Qwen2.5-Coder-1.5B on a 500K-document code corpus containing 11,566

**045**

canaries of four types and evaluated it with exposure, membership, and extraction attacks. The **046** uncontrolled results were compelling: mean exposure exceeded the panel entropy by a factor of two, **047** a sequential likelihood-ratio test flagged 99% of members after roughly one query, and verbatim **048** extraction was essentially zero. Each of these conclusions changed once the corresponding control

**049** was added (Figure 1).

**050**

| 051 052 | Three failures exposed by controls. | First, large reference-model exposure scores do not distinguish injected canaries from structurally matched canaries that were never injected. Separation stays |
|---|---|---|
| 053 |  | at chance (AUC 0.4855) even when the reference is retrained on the identical corpus with the canaries removed, at a cost of 173 GPU-hours (Section 6.3). A large raw score can therefore reflect |

[Reviewers: please read the Reviewer Guidelines (iclr.cc/Conferences/2027/ReviewerGuidelines) and the AI Policy for Reviewers (iclr.cc/Conferences/2027/AIPolicyForReviewers).](https://iclr.cc/Conferences/2027/ReviewerGuidelines) If you used AI to expand, edit, or polish your review, please provide the input text to the LLM. Better still, consider skipping the LLM and submitting your original text: we, and the authors, are much more interested in your unedited thoughts than in what an LLM has to say. AI-assisted or not, you are putting your name and reputation behind your review: LLM-generated falsehoods, hallucinations or misrepresentations are subject to disciplinary action, which may include desk-rejecting all papers you have authored.

-----

(a) Exposure (nats) (b) Member vs. non-member AUC (c) SPRT detection (%) (d) 95% upper bound, 0 hits (%)

**055** 0.6

member non-member 4 ~~3.62~~

**056**

102 0.55

| 057 | 100 | 3 |
|---|---|---|
| 058 | 0.5 | 2 |

101

**059**

0.45 1

0.53 **060** 0.11

100 0.4 0 0

**061**

T1 T2 T3 T4 All T1 T2 T3 T4 All B1 B5 Ours query query secret

**062** (W5) (W4)

**063**

**064** Figure 1: Three conclusions of an uncontrolled audit and the controls that overturn them. (a) Mean **065** reference-model exposure by canary type (log scale); the dashed line is the panel entropy H(K).

**066 (b) The same statistic separates members from never-injected non-members at chance for every type**

(AUC under the matched-corpus reference; dashed line at chance). (c) A completion-based sequential

**067**

likelihood-ratio test flags non-members as often as members under every defense. (d) For the same

**068**

zero-hit extraction data, the 95% upper bound depends on whether the statistical unit is the query or

**069**

the secret.

**070 071**

**072** effects shared by members and non-members rather than canary-specific memorization. Second, **073** a completion-based sequential likelihood-ratio test that appears to identify members accepts non- **074** members at the same rate (Section 6.4). The test responds to the likelihood shift induced by fine-tuning, **075** not to membership; without a false-positive control it would pass as a successful membership attack. **076** *Third, extraction confidence depends on the estimand. Bounds computed with the query as the* **077** unit answer whether a random prompt succeeds, whereas the security claim of interest is usually

whether a random secret is extractable. Using the canary as the unit weakens the bound by up to 34×

**078**

(Section 6.5).

**079**

**080** In each case the failure is not a weak attack or a miscomputed statistic, but a missing control or a **081** mismatch between the quantity reported and the claim it supports.

**082 083**

**Positive control and scope.** A null result is informative only if the pipeline detects leakage when **084** leakage is present. Applying the identical extraction machinery to a deliberately over-memorized **085** checkpoint recovers 10-16% of planted secrets with static and adaptive attacks (Section 6.2). We **086** nevertheless make a narrow claim. We do not conclude that the primary model memorizes nothing: **087** single insertion may fall below the detection floor, and format-level generalization may raise member **088** and non-member scores alike. We conclude that, under the audit regime we study, the uncontrolled **089** statistics do not justify the memorization interpretations they appear to support.

**090**

**091 A formal post-mortem of certification.** We correct an additive formulation whose entropy term **092** makes the bound vacuous by construction, but the pointwise likelihood ratio that reference-ratio audits **093** compute on externally generated canaries does not estimate the KL divergence the bound requires. We **094** therefore withdraw the certification claim and report budget quantities only as diagnostics (Section 4).

**095**

**096 Contributions.**

**097**

**098** • A controlled memorization audit identifying three failure modes in exposure, membership, **099** and extraction reporting (Sections 6.3-6.5). **100** • A matched-reference analysis showing that retraining the reference without the canaries **101** does not recover separation. **102** • A positive control and a minimum control set for memorization audits: matched non- **103** members, per-instrument positive controls, appropriate references, explicit estimands, and **104** per-type reporting (Section 7). **105** • A formal post-mortem of certification that corrects the entropy bound, separates two **106** leakage games, and identifies the estimator-to-divergence gap (Section 4, Appendix D). **107** • An evaluation of the accompanying defense showing that its benefit comes from a learned refusal component rather than the certificate-based architecture (Section 6.6, Appendix H).

-----

## 108 2 BACKGROUND AND RELATED WORK

**110**

**Canary-based auditing and exposure.** A canary is a synthetic sequence inserted into the training

**111**

corpus and later scored or queried under the trained model. Because the auditor knows which **112** sequences were injected, canaries provide controlled ground truth that naturally occurring secrets, **113** whose membership is uncertain, cannot. The Secret Sharer (Carlini et al., 2019) introduced rank-based **114** *exposure, which ranks the true canary among same-format candidates. Reference-model approaches* **115** instead compare the audited model with a reference. For a canary k in context c we use the pointwise **116** log-likelihood ratio

**117** *κˆ(k, c) = log pθ(k | c) - log pref(k | c),* (1)

**118**

where pθ is the audited model and pref the reference. Unlike rank-based exposure, the meaning of

**119**

*κˆ depends on the reference and on the population it is compared against. We therefore treat κˆ as a*

**120**

reference-ratio memorization diagnostic, not as a certificate.

**121 122**

**Memorization, membership, and extraction. Membership inference asks whether a specified**

**123**

example was in the training data (Shokri et al., 2017; Yeom et al., 2018); a valid test must distinguish

**124**

members from comparable non-members, so a high response rate on members alone is not evidence **125** of membership. Extraction concerns recovering training content from model outputs, either verbatim **126** or semantically. A model can assign high likelihood to a secret without emitting it under a given **127** decoding strategy, so exposure and extraction measure different things. These distinctions fix both the **128** evaluation and the statistical unit: membership requires non-members, extraction may be measured **129** per query or per secret, and exposure is interpretable only relative to a control (Appendix A.2).

**130**

**131 Related work. Language models reproduce training data at scale (Carlini et al., 2021; Nasr et al.,**

**132** 2025; Carlini et al., 2023), and code models leak credentials, personal information, and memorized **133** fragments (Huang et al., 2024; Lukas et al., 2023; Al-Kaswan et al., 2024). These studies establish **134** *whether and how much leakage occurs; we ask whether the audit itself supports the interpretation*

placed on its measurements. For membership inference, loss-ratio attacks approach chance in hard

**135**

settings (Mireshghallah et al., 2022; Duan et al., 2024), while calibrated and neighbourhood attacks

**136**

compare an example against references (Mattern et al., 2023; Zarifzadeh et al., 2024). Duan et al.

**137**

(2024) show that apparent membership performance can arise from a distribution shift between

**138**

members and non-members. We identify a complementary failure: even with structurally matched **139** non-members, a likelihood-ratio test can respond to the shift induced by fine-tuning rather than to **140** membership of the tested example. On the guarantee side, DP-SGD (Abadi et al., 2016) provides **141** worst-case record-level protection at substantial cost for large models (Anil et al., 2022; Yu et al., **142** 2022; Li et al., 2022), and privacy levels compatible with useful models need not eliminate observed **143** extraction (Lukas et al., 2023). Certified robustness (Cohen et al., 2019; Wong & Kolter, 2018) and **144** certified unlearning (Guo et al., 2020; Sekhari et al., 2021) illustrate the appeal of post-hoc guarantees **145** defined against an explicit threat model, which originally motivated LEAKCERT. We do not position

LEAKCERT as an alternative privacy guarantee. Our contribution is to identify the controls required

**146**

before empirical memorization measurements can support the security conclusions drawn from them

**147**

(Appendix A).

**148 149**

| 150 151 | 3 | THREAT MODEL AND LEAKAGE GAMES |
|---|---|---|
| 152 153 | Access: a gray-box audit. | Our attack workloads use only the sample tier that a public completion API grants (prompt in, completion out). The certificate estimator and the likelihood-ratio test |
| 154 155 |  | additionally require log pθ(k \| ck) for a specific continuation under both target and reference, i.e. the log-probability tier, which many commercial APIs expose only as truncated top-k values or not |
| 156 157 |  | at all. No component uses gradients or weights. We therefore describe LEAKCERT as a gray-box likelihood audit and do not claim that its certificate is computable by a sample-only adversary |

(Table 7, Appendix B).

**158**

**160 Two distinct games.** A tempting formulation, which we initially adopted, writes one quantity

*I(K; Y B) with K "a canary drawn from the panel" and applies Fano's inequality to it. This conflates* two experiments.

-----

**162** *Game A (panel exposure audit). A base model M0 is fine-tuned on a clean corpus C plus N canaries* **163** from a generator G with a fixed seed, Mθ = FineTune(M0, C ∪ {c1, . . . , cN }). Every canary is a **164** member and none is hidden: K ∈ {1, . . . , N} is an index over the panel, and the audited quantity is **165** an aggregate (the mean or a tail quantile) of per-canary exposures κˆk. The law on K is a bookkeeping **166** device, so conclusions concern the panel, not an individual secret. We call the object a panel-average

**167 exposure diagnostic and report the per-canary maximum separately.**

**168** *Game B (local κ-ary discrimination). For one canary slot with context c, a candidate set holds* **169** *κ structurally identical secrets (same length, charset, and generator), of which exactly one, k ⋆* , **170** was injected. Now K ∼ Uniform(Klocal) is a hidden secret, and Fano's inequality bounds the **171** probability of recovering k *⋆* after B queries. We did not run this experiment and hence report no **172** extraction-probability bound.

**173**

The alphabets differ by orders of magnitude: κ counts plausible candidates for one slot, whereas N

| 174 | reaches 104 | . Substituting N into Fano's inequality produces extraction bounds that are both vacuous |
|---|---|---|
| 175 | and mis-specified. Game B is also the game in which same-format decoys act as a control, which | is |
| 176 | the formal reason the non-member panel of Section 6.3 is the right instrument. |  |

**177**

**178 Scope.** The audit covers exposure of the injected panel only. It offers no guarantee about secrets **179** outside the panel (e.g., credentials already in the pre-training corpus) or about channels it does not **180** query, such as downstream fine-tuning or timing side channels.

**181 182**

## 4 WHAT A CERTIFICATE WOULD REQUIRE, AND WHY WE DO NOT CLAIM ONE

**183 184 185**

**186** LEAKCERT was designed to output an information-theoretic certificate: a query-budget-aware upper

bound on I(K; Y B), the information B query responses reveal about the canary index. We no longer

**187**

claim one. This section states what can be established, what the initial formulation got wrong, and

**188**

the gap between the theoretical quantity and the implemented estimator that we could not close.

**189 190**

4.1 TWO CORRECTIONS THAT DO HOLD

**191 192**

**Lemma 1 (Variational MI identity). Let K be discrete and Y a random variable with conditional**

**193** *law PY |K. For any distribution Q on the space of Y , I(K; Y ) = minQ EK[︁DKL(PY |K ∥ Q)]︁ ≤* **194** [︁DKL(PY |K ∥ Q)]︁ , with the minimum attained uniquely at Q = PY

EK *.*

**195**

**196** Lemma 1 (proof in Appendix D) justifies substituting a reference q for the uncomputable output **197** marginal PY : the reference affects the tightness of a bound built from exact KL divergences, never **198** its soundness. The property belongs to the exact expression and does not transfer automatically to **199** an empirical score (Section 4.2). Combining the lemma with the chain rule gives, for an adaptive **200** attacker issuing x1, . . . , xB with xb measurable in the history and any reference family qb,

**201**

| I(K; Y B) ≤ min {︂ H(K), ∑︁B | [︁DKL(︁ (b) | )︁]︁}︂ |
|---|---|---|
| b=1 E | p K | . |

**203**

*Remark 2 (The additive form is vacuous). The initial statement read I(K; Y B) ≤ B·DKL(pK∥qK)+*

**204**

log |K|. Under a uniform prior H(K) = log |K|, so the additive form is bounded below by H(K) for

**205**

every B ≥ 0, including B = 0 and DKL = 0. After the entropy cap that any correct implementation

**206**

must apply, it equals H(K) identically and can never exhibit the informative regime it was introduced

**207**

to describe. The error is easy to make and to miss, because the extra term reads as harmless additive **208** slack. Our implementation computed min{H(K), B · κˆ} throughout, so all reported numbers are ¯ **209** consistent with Eq. (2).

**210 211**

4.2 THE GAP WE COULD NOT CLOSE **213** Eq. (2) concerns KL divergences between full conditional output distributions. What our pipeline **214** computes, as does every reference-ratio memorization audit we are aware of, is

*κˆ* = log pθ(ki | ci) - log pref(ki | ci), (3)

*i*

-----

**216** a pointwise information density evaluated at one externally generated string ki. It estimates **217** *DKL(PY |K=i∥Q) = EY ∼PY |K=i [log p/q] only if ki is drawn from pθ(· | ci) and the expecta-* **218** tion is taken over such draws. Our canaries were generated externally and injected into training; **219** they are not samples from the target. Consequently, (i) a pointwise κˆ i can lie above or below the **220** corresponding KL; (ii) the panel mean need not estimate any expectation under the target; (iii) the **221** maximum over finitely many planted secrets does not upper-bound the KL over the completion space; **222** and (iv) clamping negative values to zero makes the statistic non-negative but does not repair the **223** sampling mismatch. Closing the gap requires either a theorem relating the canary distribution to the

target's output distribution, or a Monte Carlo estimator over draws from pθ(· | ci) whose sample

**224**

complexity for a specific multi-token secret we do not characterize. We therefore do not claim that

**225**

**the computed quantity upper-bounds I(K; Y B), and we do not present it as a certificate. We**

**226**

use κˆ as an exposure diagnostic in the sense of Carlini et al. (2019), whose interpretation Section 6.3

**227**

tests directly.

**228 229**

4.3 FURTHER WITHDRAWN CLAIMS, AND WHAT SURVIVES

**230**

**231** We also withdraw four further claims (Appendix C). (i) The extraction-probability bound, which **232** applied Fano's inequality with a panel size where the local candidate-set game (Game B) is required. **233** *(ii) High-probability concentration guarantees: canary scores share one model, one optimizer* **234** trajectory, and generator templates; the range parameter is the observed maximum rather than a **235** predetermined bound; and the Bernstein form omitted its range term. (iii) A linear utility-leakage **236** *trade-off theorem, which data processing does not imply. (iv) Optimality of the sequential probability*

*ratio test as an adaptive attacker: Wald-Wolfowitz optimality concerns the stopping rule for fixed*

**237**

distributions, not adaptive prompt selection. We retain only the measured statement:

**238**

**239 Observation 3. Across the defense configurations evaluated, we did not detect a statistically signifi-**

**240** cant utility difference at the resolution of our evaluation (n = 164 HumanEval problems, one sample

per problem, pass@1 ≈ 6-11%). This is an absence of detected effect at low power, not evidence of

**241**

absence (Section 6.6).

**242 243**

What survives is Eq. (2), Remark 2, and the vacuity threshold

**244**

**245** *B ∗ = H(K)/ κ, ˆ* (4)

**246** the budget at which a bound built from mean exposure ¯ *κˆ would reach the entropy ceiling. B∗* tells

**247**

an auditor how far a panel is from any regime in which certification is even arithmetically possible; **248** *B∗ < 1 means the ceiling is reached before the first query.*

**249 250**

## 5 EXPERIMENTAL SETUP

**251 252**

**253** The evaluation addresses three questions. Q1: Does reference-model exposure distinguish injected

canaries from matched non-members? Q2: Does the completion-based likelihood-ratio test detect

**254**

membership, or only the effect of fine-tuning? Q3: What confidence does near-zero extraction

**255**

support once the estimand is defined correctly?

**256 257**

**Training arms.** The primary target is Qwen2.5-Coder-1.5B fine-tuned for three epochs on a 500K-

**258**

document code corpus containing 11,566 canaries. The default reference is the unfine-tuned base

**259**

model. We also train a matched reference with the same architecture on the same corpus with

**260**

the canary documents removed. Because canaries are inserted as separate documents, the two **261** corpora differ by exactly those documents. Two auxiliary checkpoints serve fixed purposes: an **262** intentionally over-memorized 7B checkpoint is a positive control for the attack pipeline, and a leaky **263** *0.5B checkpoint, the only one of ours with non-zero undefended extraction, is used to compare* **264** defenses. They differ from the target in training configuration, so we use them only for these purposes **265** and never read cross-arm differences as controlled scale effects (Table 8, Appendix E.1).

**266**

**267 Canary and non-member panels. The panel contains four canary types: literal (T1, n=10,000;**

**268** AWS-shaped identifiers, JWT bodies, RSA fragments, license keys), paraphrase (T2, n=1,000; the **269** same content in base-64, language-mixed, or regex-class form), semantic (T3, n=283; algorithm

stubs, vendor protocol headers, watermarked comments), and vulnerability (T4, n=283; SQL string

-----

**271** Table 1: Per-canary exposure κˆ (nats) on the primary target (base reference, full panel, clamped), per-type entropy H, vacuity threshold B∗ (Eq. 4), the budgets at which a certificate would stay

**272**

below H, and member/non-member AUC under the matched reference (Section 6.3). Large exposure

**273**

coexists with chance-level separation for every type. The median over all canaries is 9.45 nats.

**274**

| 275 276 | Type | n | mean ¯ κˆ | max | H | B∗ | Non-vacuous at | AUC |
|---|---|---|---|---|---|---|---|---|
| 277 | T1 literal T2 paraphrase | 10,000 1,000 | 17.53 11.13 | 64.12 44.14 | 9.210 6.908 | 0.53 0.62 | - - | 0.488 0.449 |
| 278 | T3 semantic | 283 | 156.46 | 284.08 | 5.645 | 0.04 | - | 0.517 |
| 279 280 | T4 vulnerability | 283 | 1.84 | 8.29 | 5.645 | 3.06 | B ∈ {1, 2} | 0.500 |
| 281 | All | 11,566 | 19.99 | 284.08 | 9.356 | 0.47 | - | 0.4855 |

**282 283**

**284** concatenation, disabled host-key checking, unsafe deserialization). The panel entropy is H(K) = **285** ln 11,566 = 9.356 nats, and every canary is synthetic. The non-member panel is drawn from the **286** same generator with seed 999 instead of 42: identical formats, contexts, and character distributions, **287** disjoint secret values (verified by explicit set comparison), and never injected into any model. The

member side is replayed with the exact injection-time parameters and verified against the injection

**288**

manifest. Both sides use 283 canaries per type, 1,132 in total.

**289 290**

| 291 292 | Workloads, attackers, and defenses. | W2 is a synthetic credential-extraction benchmark (4,832 prompts) modelled on Huang et al. (2024), whose user-level artifacts were withheld for privacy; it is |
|---|---|---|
| 293 294 |  | a comparable benchmark, not a reproduction. W3 measures utility on HumanEval (Chen et al., 2021) (164 problems, temperature 0.2, top-p 0.95, pass@1). W4 is a code-secret suite with 7 prompts per |

canary that combines verbatim prefix probes, divergence attacks (Nasr et al., 2025), and structured-

**295**

context probes (Terraform, Dockerfiles, CI YAML). W5 rewrites each W4 prompt in five paraphrase

**296**

modes. The attackers are A-fixed (static templates), A-adaptive (UCB bandit prompt search),

**297**

A-Carlini (perplexity-ranked sampling; Carlini et al., 2021), A-greedy-LRT (the sequential **298** test of Section 6.4, at most 20 queries per canary), and the exposure estimator; the last two are also **299** run on the non-member panel. The defenses are B1 none, B2 temperature 0.5, B3 top-p 0.7, B5 a **300** content filter (a regex bank, Meli et al., 2019, plus a learned secret classifier, Saha et al., 2020), and **301** four LEAKCERT monitor configurations (Appendix H). No DP-SGD checkpoint completed training, **302** so the DP comparison is analytic only.

**303**

**304 Statistical reporting.** We report exact Clopper-Pearson intervals together with their estimand **305** and denominator; member/non-member separation as AUC with the mean gap and a Kolmogorov- **306** Smirnov statistic; and bootstrap defense comparisons with an explicitly stated resampling unit, since **307** prompts sharing a canary are not independent trials. Every bound-shaped value passes an automated **308** entropy-cap audit (Appendix G.2).

**309 310**

## 6 RESULTS

**311 312**

**313** We first report the signal an uncontrolled audit produces (Section 6.1), then verify that the pipeline **314** detects leakage when it exists (Section 6.2), and only then apply the three controls (Sections 6.3-6.5). **315** We close with the budget diagnostic, the defense, and utility (Section 6.6).

**316**

| 317 318 | 6.1 | THE EXPOSURE SIGNAL, AS AN UNCONTROLLED AUDIT REPORTS IT |
|---|---|---|
| 319 320 |  | Table 1 reports per-canary exposure on the primary target, scored against the base reference over the full panel with negative values clamped to zero, which is the estimator's default. Read without a |
| 321 322 |  | control, the mean of 19.99 nats, more than twice H(K), signals overwhelming memorization, and the type gradient spans two orders of magnitude (1.84 nats for T4 against 156.46 for T3). Both facts |
| 323 |  | are correct as arithmetic; whether either reflects memorization is settled by the last column of the table (Section 6.3). |

-----

| 325 | Table 2: Positive control. |  | The same | Table 3: Upper endpoints of exact two-sided 95% |  |  |  |
|---|---|---|---|---|---|---|---|
| 326 | pipeline recovers planted secrets from an |  |  | Clopper-Pearson intervals for zero hits (greedy decod- |  |  |  |
|  | over-memorized checkpoint. |  |  | ing). The estimand fixes the denominator. |  |  |  |
| 327 |  |  |  |  |  |  |  |
| 328 Attack 1.5B 7B Estimand Question n Upper |  |  |  |  |  |  |  |
| 329 | W4 static | 0.00% | 10.3% | Per-request, W4 | query leaks? | 700 | 0.526% |
| 330 | W4 adaptive, B=100 | 0.00% | 16% | Per-request, W5 | query leaks? | 3,500 | 0.105% |
| 331 | W5 paraphrase | 0.00% | ≈8% | Per-canary | secret leaks? | 100 | 3.622% |

---

**332**

**333**

| 334 | Table 4: Member | vs. non-member exposure | un- | Table 5: | Completion-based | SPRT | and its | false- |
|---|---|---|---|---|---|---|---|---|
| 335 | der the matched-corpus | reference (signed | LLR, | positive control | (n=100 | per panel). | TPR | and FPR |
| 336 | n = 1,132 per | side). Intervals treat | canaries | are indistinguishable, | so | the | member column | is |
|  | as exchangeable | within one training run | and | not evidence | of | membership. | Verbatim | recovery |
| 337 |  |  |  |  |  |  |  |  |
|  | therefore understate | uncertainty (Appendix | F). | is 0% | throughout. |  |  |  |
| 338 |  |  |  |  |  |  |  |  |
| 339 |  | Member | Non-member |  |  | Overall | T1 | literal |
| 340 | mean κˆ (nats) | 49.474 | 49.489 | Defense | Mem. | Non. | Mem. | Non. |
| 341 | median | 10.816 | 11.341 |  |  |  |  |  |
|  |  |  |  | B1 none | 99% | 100% | 96% | 100% |
|  | std | 78.775 | 78.149 |  |  |  |  |  |
| 342 |  |  |  | B5 filter | 94% | 90% | 80% | 72% |
|  | fraction > 0 | 99.1% | 99.5% |  |  |  |  |  |
| 343 |  |  |  | LEAKCERT | 88% | 93% | 60% | 76% |
| 344 | AUC = 0.4855, 95% | CI [0.462, 0.509] |  |  |  |  |  |  |
|  |  |  |  | mean queries to decision |  |  |  |  |
|  | gap = -0.0149 nats, CI [-6.5, +6.5]; KS = 0.049 |  |  |  |  |  |  |  |
| 345 |  |  |  | B1 none | 1.04 | 1.12 | 1.08 | 1.12 |
| 346 |  |  |  | B5 filter | 1.34 | 1.40 | 2.08 | 2.28 |
|  |  |  |  | LEAKCERT | 1.55 | 1.58 | 2.88 | 3.00 |

**347 348**

**349**

6.2 POSITIVE CONTROL: THE PIPELINE DETECTS LEAKAGE

**350**

**351** Before interpreting any null, we ran the identical W4/W5 suite (same prompts, scorer, and code) **352** against the over-memorized 7B checkpoint, trained to a loss of 0.044. The pipeline that returns 0% **353** on the 1.5B target recovers 10.3% of canaries with static templates, 16% with the adaptive attacker at **354** *B=100, and about 8% with the five paraphrase modes (Table 2). The 0% on the target is therefore a* **355** property of the model, not of the attack code. Three caveats apply: the 7B corpus has 700 documents

against the target's 500K, so this is a stress test rather than a controlled scale comparison; neither the

**356**

content filter nor LEAKCERT reduced its extraction rate, an unresolved anomaly; and its per-canary

**357**

outputs were lost, so aggregates come from the run summary (Appendix J).

**358**

**359**

6.3 CONTROL I: EXPOSURE DOES NOT SEPARATE MEMBERS FROM NON-MEMBERS

**360 361**

We scored the never-injected seed-999 panel with the same estimator and report the signed statistic, **362** since clamping would destroy the comparison. The two distributions coincide (Table 4): the mean **363** gap is -0.015 nats on a standard deviation of about 78, and the AUC interval contains 0.5. No type **364** separates (Table 1, last column): T2 scores below chance, T4 sits exactly at it, and T3, the type with **365** the largest exposure (156 nats), reaches only 0.517.

**366**

| 367 368 | A matched reference does not rescue the statistic. ence: a target-versus-base score absorbs every effect of fine-tuning on 500K documents, not only | The natural diagnosis is a confounded refer- |
|---|---|---|
| 369 370 | memorization. We tested this directly by training the matched reference (≈ 173 GPU-hours). Remov- ing the fine-tuning confound in this principled way moved the AUC by 0.005 (base: 0.49; matched: |  |

0.4855).

**371**

**372** We also audited panel independence, replay fidelity, and injector cleanliness, and found no pipeline **373** defect (Appendix E.4).

**374**

**375 Interpretation.** Two hypotheses remain, and our data cannot separate them. First, single injection **376** *may fall below the detection floor: each canary appears once in a 500K-document corpus (at most* **377** three times across training), whereas the memorization literature typically reports reliable signal only

after tens of repetitions. Second, format-level generalization may mask a smaller per-instance effect:

-----

member and non-member canaries share a small set of templates and character classes, so training **379** on 10,000 member canaries plausibly teaches the shape of a canary continuation and raises κˆ for **380** any string of that shape. Both point the same way. The claim that the target strongly memorizes its **381** canaries, which Table 1 appears to support overwhelmingly, is not sustained. This does not mean **382** the model memorizes nothing or that exposure is useless; it means that an exposure score reported **383** without a non-member panel does not license a memorization claim, even under a matched reference.

**384**

| 385 386 | 6.4 | CONTROL II: THE MEMBERSHIP TEST DETECTS FINE-TUNING |
|---|---|---|
| 387 |  | We instantiated A-greedy-LRT as a completion-based SPRT: it generates through the defense, scores each output by Λ = log ptarget(y) - log pref(y), and accepts when the cumulative ratio leaves |

**388**

the Wald band. On members the test looks highly effective (Table 5): 99% detection against the

**389**

undefended target after 1.04 queries on average. On the non-member panel, however, it returns

**390**

90-100% detection. With TPR ≈ FPR the test carries no membership information, and we retract the

**391**

membership reading. The mechanism is structural: the target is fine-tuned from the reference and the **392** scored text is generated by the target, so Λ > 0 for almost any target output regardless of membership. **393** The test reliably detects that a text came from the fine-tuned model. The defense-cost signal is also **394** membership-blind (2.88 vs. 3.00 queries on T1 members and non-members under LEAKCERT). A **395** corrected attack must score the secret's likelihood ratio, calibrated against non-members, which is **396** exactly the quantity shown to be at chance in Section 6.3.

**397**

| 398 399 | 6.5 | CONTROL III: THE ESTIMAND AND ITS DENOMINATOR |
|---|---|---|
| 400 401 |  | Verbatim extraction is 0% on the 1.5B target in every condition that completed: W4 templates, all five W5 modes, greedy and sampled decoding, and the adaptive attacker against the undefended model. |

(The adaptive attacker against the two defended configurations exceeded the wall-clock limit; those

**402**

cells are missing, not zero.) W4 issues seven prompts per canary and W5 thirty-five, over only 100

**403**

distinct canaries, and repeated probes of one secret are not independent evidence about additional

**404**

secrets. A statement such as "the target does not leak its secrets" concerns secrets, and the per-canary

**405**

bound is 6.9× and 34.4× larger than the two per-request bounds (Table 3; the one-sided values are **406** 0.427%, 0.086%, and 2.951%). Both estimands are legitimate, but the per-canary figure should carry **407** the headline. The same care applies to rounding: the sampled-decoding sweep reports 0.00%, yet **408** one of 3,500 undefended W5 prompts matched (CP 0.029%, [0.0007%, 0.159%]). We classify it as **409** an incidental pattern match, but a rounded 0.00% conceals it (Appendix E.6).

**410**

**411** 6.6 BUDGET DIAGNOSTIC, DEFENSE, AND UTILITY

**412**

**Budget diagnostic.** Following Section 4, B · κˆ is not a bound on I(K; Y ¯ *B); comparing it with the*

**413**

**414** entropy ceiling asks only whether a panel is arithmetically capable of a non-trivial bound. For the

full panel B∗ = 0.47 < 1, and after capping the quantity equals H(K) at every budget from 102 to

**415**

107 on both the 1.5B and 7B targets. Three of four types also have B∗ < 1. Only T4 stays below its

**416**

ceiling, at B ∈ {1, 2}, and its AUC is exactly 0.500: the only panel capable of a non-trivial bound is

**417**

the one the model barely memorized. The analytic Rényi DP bound Bϵ2/2 at B=104 also saturates

**418**

for every ϵ ∈ {1, 2, 4, 8, 16} (Appendix E.7).

**419 420**

**Defense.** On the 1.5B target every defense ratio is 0/0, so we compare defenses on the leaky

**421**

0.5B arm (Appendix H). Only the learned uncertainty-refusal variant reliably beats the content filter, **422** reducing paraphrase extraction from 5.98% to 2.84% over seeds 42-46 (P(B5 > ours) ≥ 0.997 per **423** seed). The full four-stage monitor does not beat the filter (P = 0.41 and 0.33 on two seeds), and **424** removing certificate accounting changes no outcome in any ablation. All measured extraction comes **425** from T4 vulnerability idioms (50.0% under B5 and 25.0% under ours; T1-T3 are 0.00% in every **426** configuration), so this arm measures suppression of vulnerability-pattern generation, not recovery of **427** planted secrets.

**428**

**429 Utility and overhead.** HumanEval pass@1 on the 1.5B target is 6.1% for both B1 and LEAKCERT, **430** with no refusals, but an earlier run of the same configuration reorders all arms, and the 4.3-8.5% **431** spread is sampling noise at n=164 (Observation 3). The refusal threshold has a sharp knee at t=0.95

(refusals ≤ 2.5%, versus 45% at t=0.7). With a median latency of 52-80 s per decision, LEAKCERT

-----

**433** Table 6: A minimum control set for canary-based memorization audits, the failure each control guards **434** against, and its effect in our audit.

**435**

| 442 | reference Explicit estimand | membership Overstated confidence from correlated | Per-canary bound 6.9-34.4× looser than |
|---|---|---|---|
| 436 437 | Control | Guards against | Effect in our audit |
|  | Matched | Reading raw scores or member-only | Exposure AUC 0.4855; SPRT FPR |
| 438 | non-members | rates as memorization | 90-100% |
| 439 | Per-instrument | Nulls caused by a weak or broken | Extraction validated on 7B (10-16%); |
| 440 | positive control Appropriate | instrument Attributing the fine-tuning shift to | exposure, SPRT not yet Matched reference moved AUC by 0.005 |
| 441 |  |  |  |
| 443 | and unit | trials | per-query |
| 444 445 | Per-type reporting | Aggregates that hide the mechanism | All defense-arm extraction is T4 idioms |

**446**

**447** is an offline audit monitor, not an inline defense. No configuration extracted any secret on the W2 **448** credential benchmark (Appendices E.8 and E.9).

**449 450**

## 7 DISCUSSION

**451 452**

**One confound, several failure modes.** Two of the failures share a single mechanism. Fine-tuning

**453**

shifts likelihood relative to the reference over broad regions of output space, so any statistic of **454** the form log ptarget(·) - log pref(·) can respond to fine-tuning even when the quantity of interest **455** is membership of a specific example. Applied to target-generated completions, the sequential test **456** responds equally to members and non-members; applied to planted secrets, exposure is large for **457** injected canaries and equally large for matched non-members. In both cases the measured shift is real, **458** but its reading as membership evidence is not. A matched-corpus reference removes the target-versus- **459** base confound without restoring separation, plausibly because of format-level generalization from **460** shared canary templates. This motivates template-disjoint non-members and per-slot near-neighbour **461** decoys (Game B), which we did not run.

**462**

**463 A minimum control set for memorization audits.** Table 6 summarizes the controls our results

argue for; each changed a conclusion of our own audit.

**464 465**

**Separation and vacuity.** Eq. (2) requires exact divergences that our pointwise statistic does not

**466**

instantiate, and the same statistic fails to separate members from non-members. The first prevents

**467**

certification; the second questions whether the statistic carries a membership signal at all. We

**468**

therefore recommend reporting separation (does the statistic distinguish members from matched **469** non-members?) together with vacuity (could certificate-style accounting remain below the entropy **470** ceiling, i.e. is B∗ ≥ 1?). Neither is a certificate. For deployment, a low extraction rate is not evidence **471** of safety, nor is a large exposure score evidence of memorization; decisions should rest on controlled, **472** comparative evidence.

**473**

**474 Limitations.** All member/non-member evidence comes from one target/reference training pair, one **475** model scale, and one injection regime, and the positive control validates extraction only; Appendix F **476** discusses these and further limitations.

**477**

| 478 479 | 8 | CONCLUSION |
|---|---|---|
| 480 481 | We set out to certify memorization leakage in fine-tuned code models and found that the audit itself needed controls: exposure did not separate members from matched non-members, a likelihood-ratio |  |
| 482 483 | test detected fine-tuning rather than membership, and extraction confidence changed by up to 34× with the estimand. Because pointwise exposure does not estimate the divergence a certificate requires, |  |
| 484 485 | we make no certification claim. Memorization audits should report member/non-member separation rather than raw scores, validate each instrument with its own positive control, and state the estimand |  |

and unit behind every confidence claim.

-----

AI USE STATEMENT

**488 Synthetic data generation. We used ChatGPT 5.6 (OpenAI) to generate the synthetic canary data:**

**489** the credential-shaped strings, paraphrased variants, semantic stubs, and insecure-code idioms that **490** make up the four canary types described in Section 5. No canary was derived from real credentials, **491** real repositories, or user data. We assembled the member and non-member panels, injected the **492** canaries, and verified panel disjointness with our own pipeline (Appendix G.5).

**493 Research design, theory, and implementation. Generative AI tools were not used to design**

**494** the study, to develop the theoretical analysis, or to formulate the mathematical claims and proofs **495** (Section 4 and Appendix D). All training, attack, and evaluation code was written by the authors, and **496** all experiments and analyses were conducted by the authors.

**497**

**Writing assistance. Generative AI tools were used for language editing and for adapting the**

**498** manuscript to the ICLR 2027 template. We reviewed all AI-assisted material and take full responsi- **499** bility for the content of this paper, including all text, claims, and artifacts.

**500 501**

ETHICS STATEMENT

**502**

**503** All canaries are synthetic: credential-shaped canaries imitate only the format of real credential types, **504** and none is or has been valid for any account, service, or person. No real user data, live credential, or **505** third-party secret was created, handled, or placed at risk, and no human subjects are involved. The **506** credential-extraction artifacts of Huang et al. (2024) contain real user-level data and were withheld **507** by their authors; we did not attempt to reconstruct them, and our comparable benchmark is fully **508** synthetic. Vulnerability canaries are short, widely documented anti-patterns, not exploits. The attacks

we implement are established in the literature, and our principal offensive-side findings are negative,

**509**

so publishing them protects practitioners from acting on flawed audit evidence rather than increasing

**510**

attacker capability. Because canary strings resemble credentials, we release deterministic regeneration

**511**

scripts instead of raw files. We also report corrected and retracted claims, including failures of our

**512**

own defense configurations, as an obligation of measurement work. Appendix I gives the full ethics **513** considerations.

**514 515**

REPRODUCIBILITY STATEMENT

**516**

**517** Section 5 and Appendices E.1 and G describe the training arms, canary and non-member panel **518** construction, workloads, attackers, defenses, the exposure estimator, and the exact Clopper-Pearson **519** computation. Complete proofs of Lemma 1 and Eq. (2), together with the computed (non-validated) **520** concentration expressions, are in Appendix D. An anonymous artifact containing the pipeline, **521** configurations with fixed seeds, per-run result files for every table and figure, and a single entry point **522** that reproduces the central member/non-member result from released checkpoints is described in **523** Appendix J, which also lists the artifacts that were lost and cannot be released.

**524**

## 525 REFERENCES

**526**

**527** Martin Abadi, Andy Chu, Ian Goodfellow, H. Brendan McMahan, Ilya Mironov, Kunal Talwar, **528** and Li Zhang. Deep learning with differential privacy. In ACM Conference on Computer and

*Communications Security (CCS), 2016.*

**529 530**

Ali Al-Kaswan, Maliheh Izadi, and Arie van Deursen. Traces of memorisation in large language

**531**

models for code. In IEEE/ACM International Conference on Software Engineering (ICSE), 2024.

**532**

doi: 10.1145/3597503.3639133.

**533**

**534** Rohan Anil, Badih Ghazi, Vineet Gupta, Ravi Kumar, and Pasin Manurangsi. Large-scale differ- **535** entially private BERT. In Findings of the Association for Computational Linguistics: EMNLP, **536** 2022. **538** Nicholas Carlini, Chang Liu, Ulfar Erlingsson, Jernej Kos, and Dawn Song. The secret sharer: **539** evaluating and testing unintended memorization in neural networks. USENIX Security Symposium,

2019.

-----

Nicholas Carlini, Florian Tramer, Eric Wallace, Matthew Jagielski, Ariel Herbert-Voss, Katherine **541** Lee, Adam Roberts, Tom Brown, Dawn Song, Ulfar Erlingsson, et al. Extracting training data **542** from large language models. In USENIX Security Symposium, 2021.

**543**

**544** Nicholas Carlini, Daphne Ippolito, Matthew Jagielski, Katherine Lee, Florian Tramer, and Chiyuan **545** Zhang. Quantifying memorization across neural language models. In International Conference on

*Learning Representations (ICLR), 2023.*

**546 547**

Mark Chen, Jerry Tworek, Heewoo Jun, Qiming Yuan, Henrique Ponde de Oliveira Pinto, Jared **548** Kaplan, Harri Edwards, Yuri Burda, Nicholas Joseph, Greg Brockman, et al. Evaluating large **549** language models trained on code. In arXiv preprint arXiv:2107.03374, 2021.

**550**

**551** Jeremy M. Cohen, Elan Rosenfeld, and J. Zico Kolter. Certified adversarial robustness via randomized **552** smoothing. In International Conference on Machine Learning (ICML), 2019.

**553**

Michael Duan, Anshuman Suri, Niloofar Mireshghallah, Sewon Min, Weijia Shi, Luke Zettlemoyer, **554** Yulia Tsvetkov, Yejin Choi, David Evans, and Hannaneh Hajishirzi. Do membership inference

**555** attacks work on large language models? In Conference on Language Modeling (COLM), 2024.

**556**

**557** Chuan Guo, Tom Goldstein, Awni Hannun, and Laurens van der Maaten. Certified data removal from **558** machine learning models. In International Conference on Machine Learning (ICML), 2020.

**559**

Yizhan Huang, Yichen Li, Weibin Wu, Jianping Zhang, and Michael R. Lyu. Your code secret belongs

**560**

to me: neural code completion tools can memorize hard-coded credentials. Proceedings of the **561** *ACM on Software Engineering, 1(FSE):2515-2537, 2024. doi: 10.1145/3660818.*

**562**

**563** Matthew Jagielski, Milad Nasr, Katherine Lee, Christopher A. Choquette-Choo, Nicholas Carlini, **564** and Florian Tramer. Students parrot their teachers: membership inference on model distillation. In **565** *Advances in Neural Information Processing Systems (NeurIPS), 2023.*

**566**

Xuechen Li, Florian Tramer, Percy Liang, and Tatsunori Hashimoto. Large language models can be

**567**

strong differentially private learners. In International Conference on Learning Representations **568** *(ICLR), 2022.*

**569**

**570** Nils Lukas, Ahmed Salem, Robert Sim, Shruti Tople, Lukas Wutschitz, and Santiago Zanella- **571** Béguelin. Analyzing leakage of personally identifiable information in language models. In IEEE **572** *Symposium on Security and Privacy (S&P), 2023.*

**573**

Justus Mattern, Fatemehsadat Mireshghallah, Zhijing Jin, Bernhard Schölkopf, Mrinmaya Sachan,

**574**

and Taylor Berg-Kirkpatrick. Membership inference attacks against language models via neigh- **575** bourhood comparison. In Findings of the Association for Computational Linguistics: ACL, 2023.

**576**

**577** Michael Meli, Matthew R. McNiece, and Bradley Reaves. How bad can it git? characterizing secret **578** leakage in public github repositories. In Network and Distributed System Security Symposium **579** *(NDSS), 2019.*

**580**

Fatemehsadat Mireshghallah, Kartik Goyal, Archit Uniyal, Taylor Berg-Kirkpatrick, and Reza Shokri.

**581**

Quantifying privacy risks of masked language models using membership inference attacks. In **582** *Conference on Empirical Methods in Natural Language Processing (EMNLP), 2022.*

**583**

**584** Milad Nasr, Javier Rando, Nicholas Carlini, Jonathan Hayase, Matthew Jagielski, A. Feder Cooper, **585** Daphne Ippolito, Christopher A. Choquette-Choo, Florian Tramer, and Katherine Lee. Scalable **586** extraction of training data from aligned, production language models. In International Conference

*on Learning Representations (ICLR), 2025.*

**587**

**588**

Aakanksha Saha, Tamara Denning, Vivek Srikumar, and Sneha Kumar Kasera. Secrets in source code: **589** reducing false positives using machine learning. In International Conference on Communication

**592** Ayush Sekhari, Jayadev Acharya, Gautam Kamath, and Ananda Theertha Suresh. Remember what **593** you want to forget: algorithms for machine unlearning. In Advances in Neural Information

*Processing Systems (NeurIPS), 2021.*

-----

Reza Shokri, Marco Stronati, Congzheng Song, and Vitaly Shmatikov. Membership inference attacks

**595** against machine learning models. In IEEE Symposium on Security and Privacy (S&P), 2017.

**596**

**597** Eric Wong and J. Zico Kolter. Provable defenses against adversarial examples via the convex outer **598** adversarial polytope. In International Conference on Machine Learning (ICML), 2018.

**599**

**600** Samuel Yeom, Irene Giacomelli, Matt Fredrikson, and Somesh Jha. Privacy risk in machine learning:

analyzing the connection to overfitting. In IEEE Computer Security Foundations Symposium (CSF),

**601**

2018.

**602 603**

Da Yu, Saurabh Naik, Arturs Backurs, Sivakanth Gopi, Huseyin A. Inan, Gautam Kamath, Janardhan **604** Kulkarni, Yin Tat Lee, Andre Manoel, Lukas Wutschitz, et al. Differentially private fine-tuning of **605** language models. In International Conference on Learning Representations (ICLR), 2022.

**606**

**607** Sajjad Zarifzadeh, Philippe Liu, and Reza Shokri. Low-cost high-power membership inference **608** attacks. In International Conference on Machine Learning (ICML), 2024.

**609 610**

## 611 A EXTENDED BACKGROUND AND RELATED WORK

**612**

**613** This appendix gives the full background and related-work discussion summarized in Section 2.

**614**

| 615 616 | A.1 | CANARY-BASED MEMORIZATION AUDITING |
|---|---|---|
| 617 618 |  | Canary-based auditing provides controlled ground truth for studying memorization in language models. A synthetic sequence, or canary, is inserted into the training corpus and subsequently |
| 619 |  | queried or scored under the trained model. Because the auditor knows which sequences were injected, canaries make it possible to study memorization without relying on naturally occurring secrets whose |

**620**

training membership may be uncertain.

**621**

**622** The Secret Sharer framework (Carlini et al., 2019) introduced exposure as a measure of how strongly **623** a model prefers an injected canary relative to a population of structurally similar candidates. Classical **624** exposure is rank-based: the true canary is ranked according to its model likelihood or perplexity **625** among same-format alternatives. A highly exposed canary is therefore one that the model assigns

unusually high preference relative to its candidate set.

**626**

**627** Reference-model approaches instead compare the likelihood assigned by a target model with that **628** assigned by a reference model. For a canary k appearing in context c, we use the pointwise log- **629** likelihood ratio of Eq. (1), where pθ denotes the audited model and pref the reference. This statistic **630** measures how much more strongly the target model prefers a particular continuation than the reference **631** model. Unlike classical rank-based exposure, however, its interpretation depends on the choice of

reference and on what comparison population is used. Throughout this paper, we therefore treat κˆ as

**632**

a reference-ratio memorization diagnostic rather than as a certificate by itself.

**633 634**

**635** A.2 MEMORIZATION, MEMBERSHIP, AND EXTRACTION

**636**

We distinguish several notions that are related but not equivalent.

**637**

**638** *Memorization refers broadly to model behavior that depends on particular training examples. In* **639** this paper, membership inference asks whether a specified example was present in the training data, **640** without requiring recovery of its content (Shokri et al., 2017; Yeom et al., 2018). A successful **641** membership test must therefore distinguish members from comparable non-members; a high response

rate on members alone is insufficient.

**642**

**643** *Extraction instead concerns recovery of training content from model outputs. We distinguish verbatim* **644** *extraction, in which the injected sequence is reproduced exactly, from semantic extraction, in which* **645** equivalent information is recovered under a different surface form. These notions should not be **646** conflated with exposure: a model can assign high likelihood to a secret without emitting it under a **647** particular decoding strategy, while successful extraction is direct evidence that the corresponding

information is recoverable.

-----

These distinctions determine both the appropriate evaluation and the statistical unit of analysis. **649** Membership requires comparison against non-members; extraction may be measured per query or **650** per secret depending on the security question; and exposure is a continuous score whose magnitude **651** is meaningful only relative to an appropriate control.

**652**

| 653 654 | A.3 | MEMORIZATION AND EXTRACTION IN LANGUAGE AND CODE MODELS |
|---|---|---|
| 655 656 |  | Canary-based memorization measurement was popularized by the Secret Sharer framework (Carlini et al., 2019), which inserts high-entropy sequences into training data and measures their exposure |
| 657 658 |  | relative to same-format alternatives. Subsequent work demonstrated that language models can reproduce training data at substantially larger scale. Carlini et al. (2021) recover training examples |

from GPT-2 using generation followed by reference-model perplexity ranking, while later divergence

**659**

attacks extend extraction to aligned production models (Nasr et al., 2025). Other work studies how

**660**

memorization changes with model and dataset scale (Carlini et al., 2023).

**661**

**662** Code models introduce particularly security-relevant forms of memorization because their training **663** corpora may contain credentials, licensed fragments, and insecure code. Prior studies document **664** leakage of credentials and personally identifying information as well as memorized code fragments

(Huang et al., 2024; Lukas et al., 2023; Al-Kaswan et al., 2024). These works primarily establish

**665**

whether memorization or extraction occurs and how much can be recovered. Our focus is comple-

**666**

mentary: we study whether the audit itself supports the interpretation assigned to its measurements.

**667**

In particular, we examine how reference-ratio scores behave relative to matched non-members and

**668**

how the choice of statistical estimand affects conclusions drawn from extraction experiments.

**669**

**670** A useful distinction arises from the original Secret Sharer design. Its same-format candidate population provides a direct comparison between the injected canary and alternative strings. A standalone

**671**

reference-model likelihood ratio does not provide the same member/non-member comparison auto-

**672**

matically. Our results motivate making such controls explicit when reference-ratio statistics are used

**673**

as evidence of memorization.

**674**

**675**

A.4 MEMBERSHIP INFERENCE AND EVALUATION CONTROLS

**676 677**

Membership inference asks whether an example appeared in a model's training data (Shokri et al.,

**678**

2017; Yeom et al., 2018). Likelihood- and loss-based attacks have been widely studied for language **679** models, but their effectiveness becomes less clear at modern model scales. Several studies report that **680** simple loss-ratio attacks approach chance in challenging settings (Mireshghallah et al., 2022; Duan **681** et al., 2024), while calibrated and neighbourhood-based approaches attempt to improve separation by **682** comparing an example with suitable references (Mattern et al., 2023; Zarifzadeh et al., 2024).

**683**

Of particular relevance, Duan et al. (2024) show that apparent membership-inference performance

**684**

can result from weak evaluation practice, especially when members and non-members come from **685** different distributions. Our work identifies a complementary failure mode. Even when non-members **686** are generated from the same structure as members, a likelihood-ratio test may respond to the **687** distributional shift created by fine-tuning rather than to membership of the specific example. This **688** reinforces the need to evaluate both true- and false-positive behaviour under carefully matched **689** member and non-member populations.

**690**

| 691 692 | A.5 | PRIVACY GUARANTEES AND CERTIFIED DEFENSES |
|---|---|---|
| 693 694 |  | Differential privacy provides a fundamentally different form of protection. DP-SGD (Abadi et al., 2016) gives a worst-case, data-independent record-level privacy guarantee, although achieving strong |
| 695 696 |  | privacy can impose substantial utility and computational costs for large language and code models (Anil et al., 2022; Yu et al., 2022; Li et al., 2022). Empirical work also shows that privacy parameters |

compatible with useful model quality do not necessarily eliminate observed extraction (Lukas et al.,

**697**

2023), while knowledge distillation does not in general remove memorized information (Jagielski

**698**

et al., 2023). We therefore view empirical memorization auditing as complementary to, rather than a replacement for, differential privacy. **701** Our original motivation is also related to the work on certified defenses. Certified robustness methods

provide guarantees against specified perturbation classes through techniques such as randomized

-----

**703** Table 7: Access tiers. The certificate needs strictly more than a public completion API provides.

| 704 705 | Tier | Access | Used for |
|---|---|---|---|
|  | Sample | prompt → completion | W2/W4/W5 attacks |
| 706 | Log-prob | log p(target \| prompt) | certificate, LRT |
| 707 708 | White-box | gradients / weights | not used |

**709**

**710** smoothing (Cohen et al., 2019) and convex relaxations (Wong & Kolter, 2018), while certified **711** unlearning aims to guarantee the effect of removing training data (Guo et al., 2020; Sekhari et al., **712** 2021). These approaches illustrate the appeal of a post-hoc guarantee defined relative to an explicit

threat model.

**713**

**714** LEAKCERT was initially motivated by an analogous goal: to relate a query budget to information **715** revealed about injected secrets. Our analysis ultimately exposes an important distinction between such **716** formal guarantees and empirical memorization scores. A valid information-theoretic bound requires **717** a well-defined divergence over model output distributions; a pointwise likelihood ratio evaluated on **718** externally generated canaries does not automatically estimate that quantity. Consequently, we do

not position LEAKCERT as an alternative privacy guarantee. Instead, our contribution is to identify

**719**

the conditions and controls required before empirical memorization measurements can support the

**720**

security conclusions drawn from them.

**721 722**

## 723 B THREAT MODEL AND LEAKAGE GAMES IN FULL

**724**

**725** Two modelling choices in this section fix errors that are easy to make and hard to see: what access **726** the auditor actually needs, and what random experiment the mutual information refers to.

**727**

**728** B.1 ACCESS TIERS: THIS IS A GRAY-BOX AUDIT

**729**

Certificates of this kind are often called "black-box." That is imprecise. Table 7 separates three tiers.

**730**

Our attack workloads operate at the sample tier, which is what a public completion API grants. The

**731**

certificate estimator requires log pθ(k | ck) for a specific continuation under both target and reference:

**732**

the log-probability tier, which many commercial APIs do not expose, or expose only as truncated **733** top-k values. We therefore describe LEAKCERT as a gray-box likelihood audit and do not claim **734** the certificate is computable by a sample-only adversary. Estimating the probability of a specific **735** multi-token secret by sampling alone has a sample complexity we do not characterize; we flag it as **736** open (Appendix F).

**737**

| 738 739 | B.2 | TWO DISTINCT GAMES |
|---|---|---|
| 740 741 | Prior formulations (including our own earlier one) write a single quantity I(K; Y B) with K "a canary drawn from the panel" and then apply Fano's inequality to bound the probability an attacker |  |

guesses K. This conflates two experiments differing in what is random and in the size of the relevant

**742**

alphabet.

**743 744**

**Game A: panel exposure audit. Fix a base model M0, a clean corpus C, and a panel of N canaries**

**745**

from generator G with fixed seed. The target is Mθ = FineTune(M0, C ∪ {c1, . . . , cN }). Every

**746**

canary is a member; none is hidden. Here K ∈ {1, . . . , N} is an index over the panel, not a **747** hidden secret, and the audited quantity is an aggregate: the mean, or a tail quantile, of per-canary **748** exposures κˆk. The uniform (or π-weighted) law on K is a bookkeeping device letting us apply mutual- **749** information machinery to N per-canary quantities; it does not correspond to a physical situation in **750** which one secret among N was selected. Eq. (2) lives in Game A, and its conclusion concerns the **751** panel, not any individual secret. This is why we call the object a panel-average exposure diagnostic: **752** per-canary exposures can and do exceed the panel mean, and we report the maximum separately as **753** an uncapped diagnostic. **755 Game B: local κ-ary discrimination.** Fix one canary slot with context c. Define a candidate set of

*κ structurally identical secrets (same length, charset, and generator) of which exactly one, k ⋆* , was

-----

**756** injected and the remaining κ - 1 never appeared in any corpus. Now K ∼ Uniform(Klocal) is a **757** hidden secret in the cryptographic sense, and Fano's inequality would apply to the probability of **758** recovering k *⋆* after B queries. We did not run such an experiment, which is why this paper reports no **759** extraction-probability bound (Section 4.3).

**760**

**761 Why the separation matters.** The alphabet sizes differ by orders of magnitude: κ counts plausible **762** candidates for one slot, while N reaches 104 . Substituting the panel size N into the Fano bound (as **763** a single shared "canary set size" parameter invites) inflates the denominator and yields extraction **764** bounds that are simultaneously vacuous and mis-specified. Game B is also the game in which the **765** Secret Sharer's same-format decoys act as a control, which is the formal reason the non-member

panel of Section 6.3 is the right instrument.

**766 767**

**768** B.3 SCOPE

**769**

The audit covers exposure of the injected panel only. It offers no formal guarantee about secrets

**770**

never part of the panel (for instance real credentials already in the pre-training corpus), nor about

**771**

channels the audit does not query, such as behaviour after downstream fine-tuning or side channels **772** such as timing. The panel is designed to be representative of a class of structured secrets, but **773** representativeness is an empirical design choice, not a theorem.

**774 775**

## C THE CERTIFICATE POST-MORTEM IN FULL

**776 777**

We present the certificate analysis of Section 4 in full because the gap it identifies is easy to overlook;

**778**

we overlooked it ourselves, and it is the reason the budget numbers in Section 6.6 are reported as

**779**

diagnostics rather than guarantees.

**780 781**

**Reference substitution.** Lemma 1 answers a question the reference-model approach otherwise

**782**

leaves open: why is it legitimate to substitute a reference q for the true output marginal PY , which is

**783**

not computable? Because the inequality holds for every Q, the choice of reference affects the tightness **784** of a bound built from exact KL divergences, never its soundness. We flag, because we previously **785** blurred this, that the property belongs to the exact expression and does not transfer automatically to **786** any empirical score computed against a reference.

**787**

**788 On the additive form.** The mistake recorded in Remark 2 is easy to make and survives review: **789** it is off by a term that reads as harmless additive slack. Because our implementation computed

min{H(K), B · κˆ} all along, the published numbers were consistent with Eq. (2) and not with the ¯

**790**

**791** stated theorem, a discrepancy a reader checking arithmetic against the theorem would find, and that **792** we should have found earlier.

**793**

**794 Consequences of the estimator gap.** Because the canaries are not samples from the target's output

distribution:

**795 796**

- a pointwise κˆ i can lie above or below the corresponding KL, in either direction;

**797**

- the mean over a synthetic panel need not estimate any expectation under the target distribu-

**798**

tion;

**799**

- the maximum over finitely many planted secrets does not upper-bound the KL over the full **800** completion space; and **801** • clamping negative values to zero does not repair the sampling mismatch: it only makes the **802** statistic non-negative.

**803**

**804** Eq. (2) therefore appears in this paper as a statement of what a certificate would have to satisfy, and κˆ **805** as an exposure diagnostic in the sense of Carlini et al. (2019).

**806**

| 807 | C.1 | FOUR FURTHER CLAIMS WE WITHDRAW |
|---|---|---|
| 809 |  | The extraction-probability bound. We previously converted the panel quantity into an extraction probability via Fano's inequality with denominator log κ, and instantiated κ with a canary-type panel |

-----

**810** size. Fano's inequality applies to a κ-ary guessing game in which exactly one of κ structurally **811** identical candidates was injected and the rest never appeared in training. Our panels are not that: **812** all 283 vulnerability canaries, for instance, are members, occupying different slots. We ran no local **813** candidate-set experiment, so we withdraw the extraction-probability bound entirely and report the **814** budget analysis of Section 6.6 without converting it.

**815**

**816 Concentration as a high-probability guarantee.** Hoeffding- and Bernstein-style concentration **817** over per-canary scores requires assumptions our setting violates. All canaries are injected into one **818** corpus and one model, so their scores share parameters, optimizer trajectory, and (critically) generator

templates, which is precisely the dependence Section 6.3 identifies empirically. Separately, the

**819**

range parameter κmax we use is the observed sample maximum, not a predetermined bound, which

**820**

Hoeffding requires; and the Bernstein expression we reported omits the standard range-dependent

**821**

*O(log(1/δ)/n) term. We therefore do not claim validated 1 - δ coverage for any quantity in this*

**822**

paper, and we report the concentration expressions in Appendix D only to document what was **823** computed.

**824**

| 825 | A utility-leakage trade-off theorem. | We previously asserted that any decoding-time defense |
|---|---|---|
| 826 | reducing leakage by factor ρ must increase | task error by at least ρcT. Data processing establishes |
| 827 | only that neither I(K; Y ) nor I(XT ; Y ) | increases under post-processing; it does not imply a linear |
| 828 | trade-off, and with cT unconstrained the | statement is either unproven or empty. We withdraw it and |
| 829 | retain only what we measured, stated as | Observation 3 in Section 4.3. |

**830**

We similarly withdraw an earlier claim that a sequential probability ratio test is the optimal adaptive **831** attacker. Wald-Wolfowitz optimality concerns the stopping rule for observations from fixed distri- **832** butions; it says nothing about adaptive selection of prompts that induce different distributions. Our **833** adaptive attacker is a UCB bandit, and we make no optimality claim for it. We also correct a sign **834** error: under the null the normalized likelihood-ratio process has non-positive conditional drift and is **835** a supermartingale, not a submartingale.

**836**

## 837 D PROOFS AND COMPUTED EXPRESSIONS

**838 839**

This appendix proves the two results Section 4 claims (Lemma 1 and Eq. (2)) and then documents, **840** without claiming validity, the concentration expressions our pipeline computed. The separation is **841** deliberate: the first part is established, the second is not.

**842**

**843** LEMMA 1 (VARIATIONAL MI IDENTITY)

**844**

**845** *Proof. Let PK,Y be the joint law and PY the true marginal of Y.* By definition I(K; Y ) = **846** EK[DKL(PY |K ∥ PY )]. For an arbitrary Q on the space of Y , decompose pointwise:

**847**

*PY |K PY |K + log PY* **848** log = log *.*

*Q PY Q*

**849**

**850** Taking expectation under PK,Y , the first term gives I(K; Y ) and the second gives DKL(PY ∥Q), **851** since it does not depend on K and the marginal of Y under PK,Y is PY . Hence

**852**

EK [︁DKL(PY |K ∥ Q)]︁ - I(K; Y ) = DKL(PY ∥ Q) ≥ 0

**853**

**854** by Gibbs' inequality, with equality iff Q = PY almost everywhere. Minimizing over Q gives the **855** identity; dropping the minimum gives the upper bound for every Q.

**856**

**857** *Scope. The inequality holds for any Q, so a poorly chosen reference costs tightness but not soundness* **858** *when the quantity computed is the exact KL divergence. It says nothing about a pointwise score of* **859** the form Eq. (3); see Section 4.2.

**860**

**861** EQUATION (2) (ENTROPY-CAPPED BUDGET BOUND)

*Proof. By the chain rule for mutual information, I(K; Y B) = ∑︁B b=1 I(K; Yb | Y<b). Fix b and* condition on Y<b = y<b. Applying Lemma 1 to the conditional joint law of (K, Yb) given y<b, with

-----

**864** *Q = qb(· | y<b),*

*I(K; Yb | Y<b=y<b) ≤ EK[DKL(pK(· | y<b) ∥ qb(· | y<b))] .*

**866**

The prompt xb is a measurable function of y<b, so conditioning on the history is legitimate and the

**867**

data-processing step through xb applies. Taking expectation over Y<b and summing over b yields the

**868**

right-hand branch. The left-hand branch is the entropy bound I(K; Y B) ≤ H(K), valid for discrete **869** *K because I(K; Y B) = H(K) - H(K | Y B) and conditional entropy is non-negative. Both hold* **870** simultaneously, so their minimum does. The same argument holds for K ∼ π arbitrary, replacing **871** log |K| by Hπ(K) and the per-query term by its π-weighted expectation.

**872**

**873** *On the additive form. Writing the conclusion as B · DKL + log |K| rather than min{H(K), B · DKL}* **874** replaces a ceiling by a floor. Under a uniform prior the additive expression is at least log |K| = H(K) **875** for all B ≥ 0, so after the entropy cap it is identically H(K) and can never be informative (Remark 2).

**876**

*On the prompt. Eq. (2) assumes xb depends on K only through the observed history. In Game A*

**877**

(Section 3) an auditor who queries the canary context cK violates this, since the prompt then depends **878** on K directly. Either the conditional law PY |K must be defined to include that dependence, or the **879** audit must be restricted to prompts chosen without knowledge of K. We flag this as an unresolved **880** specification issue rather than papering over it: it is one reason we do not present the computed **881** quantity as a bound (Section 4.2).

**882**

**883** COMPUTED CONCENTRATION EXPRESSIONS (NOT VALIDATED)

**884**

**885** For completeness we record what the pipeline computed. Let κˆ1, . . . , κˆ n be per-canary exposures

and κmax = maxi κˆ . The Hoeffding-style expression is

**886** *i*

**887** *Lˆ︁ B = min{︂ H(K), B(︁ n + κmax√︂* log(2/δ) )︁}︂

*κˆ ,*

2n

**888**

**889** and the Bernstein-style variant replaces the slack with σ √︁2 log(2/δ)/n for σ the sample standard **890** deviation. On the T4 sub-panel at δ=0.01 these evaluate to 2.645 and 2.242 nats at B=1.

**891 These are not validated 1 - δ certificates, for three independent reasons, each sufficient on its**

**892** own. (i) The κˆ i are not independent: all canaries were injected into one corpus and one model, so **893** their scores share parameters, optimizer trajectory, and generator templates, and template sharing is **894** precisely the dependence Section 6.3 identifies empirically. (ii) Hoeffding requires a predetermined **895** support bound; κmax is the observed sample maximum, used without correction. (iii) The Bernstein **896** expression omits the standard range-dependent O(κmax log(1/δ)/n) term, so it is not the Bernstein **897** bound even under independence. Repairing these requires independently trained models for clusterlevel inference and a predetermined clipping bound, neither of which we have. We report the numbers

**898**

only to document the computation behind Table 1.

**899 900**

VACUITY THRESHOLD

**901**

**902** Setting the computed quantity equal to the ceiling, B ·κˆ = H(K), gives Eq. (4), B∗ = H(K)/κˆ. For ¯ **903** *κ > Hˆ* (K) we get B∗ < 1, so the expression saturates before the first query. Table 1 instantiates this **904** per type; the measured crossing for T4 at B = 5 is consistent with B∗ = 5.6454/1.8435 = 3.06.

**905 906**

## E ADDITIONAL SETUP DETAILS AND RESULTS

**907 908**

This appendix collects setup details, figures, and tables that support Sections 5 and 6 but did not fit in

**909**

the main text.

**910 911**

E.1 TRAINING ARMS, WORKLOADS, AND STATISTICAL REPORTING

**912**

**913** Table 8 summarizes the checkpoints used throughout the evaluation. Two additional checkpoints **914** serve distinct purposes. An intentionally over-memorized 7B checkpoint provides a positive control **915** for the extraction pipeline, while a leaky 0.5B checkpoint provides a non-degenerate setting for **916** evaluating defenses because its undefended extraction rate is non-zero. These auxiliary arms differ **917** from the primary target in training configuration; we therefore use them only for their stated purposes

and do not interpret cross-arm differences as controlled model-scale effects.

-----

**919** Table 8: Training arms. Corpus mismatch between the primary target and the 7B and leaky-0.5B **920** arms is a confound we do not attempt to apportion (Appendix F). "GPU-h" is wall-clock × devices

for the final run; † the primary target's device count was not recorded, so we give wall-clock only; ‡

**921**

the leaky 0.5B arm's corpus size and epoch count were not recorded in the released run metadata

**922**

("n.r."), which is a reproducibility gap we flag rather than reconstruct: its evaluation panels held 4-8

**923**

canaries per type depending on seed.

**924**

Arm Model Corpus Canaries Epochs GPU-h Used in

**925**

Primary target Qwen2.5-Coder-1.5B 500K docs 11,566 (seed 42) 3 45 h† Sections 6.1-6.6

**926**

|  | Matched reference | Qwen2.5-Coder-1.5B | same 500K docs | none | 3 | ≈173 | Section 6.3 |
|---|---|---|---|---|---|---|---|
| 927 | Base reference | Qwen2.5-Coder-1.5B | - (not fine-tuned) | - | 0 | - | Section 6.1, 6.3 |
| 928 | Over-memorized 7B | Qwen2.5-Coder-7B | 700 docs | 11,566 | 1 | - | Section 6.2, 6.6 |
|  | Leaky 0.5B | Qwen2.5-Coder-0.5B | seeded panels‡ | 4-8/type | n.r.‡ | - | Sections 6.6-E.9 |

**929 930**

---

**931**

*κ¯ˆ by type* 156.46

**932** 102

---

*H(K) = 9.356*

**933 934**

9.36 9.36 9.36 9.36 9.36

101

---

**935**

**936** 1.84

**937** 100

---

**938** T1 T2 T3 T4 All

**939**

**940** Figure 2: Exposure by canary type (log scale) against the panel entropy ceiling. Three of four types **941** sit above H(K); only vulnerability canaries (T4) fall below it, which is what makes T4 the sole type **942** whose budget diagnostic is non-vacuous (Section 6.6).

**943 944**

**Workloads. W2 is a credential-extraction benchmark modelled on the study by Huang et al. (2024)**

**945**

of hard-coded credentials memorized by neural code completion tools. Their extraction artifacts are **946** user-level and were withheld for privacy, so we generate 4,832 synthetic prompts with controlled **947** ground truth and report this as a comparable benchmark, never a reproduction of their findings.

**948 W3 measures utility in HumanEval (Chen et al., 2021) (164 problems, temperature 0.2, top-p 0.95,**

**949** pass@1, identical checkpoint across defenses). W4 is a code-secret suite over a stratified evaluation **950** subset (7 prompts per canary) combining verbatim prefix probes, divergence attacks (Nasr et al., **951** 2025), and structured-context probes (Terraform, Dockerfiles, CI YAML). W5 rewrites each W4 **952** prompt in five paraphrase modes (template variation, language variation, regex character class,

natural-language description, and base64-decode variation), giving 5× the prompts.

**953 954**

**955 Statistical reporting.** We report exact Clopper-Pearson intervals and state the estimand and

denominator for each (Section 6.5). Member/non-member separation is reported as AUC with the

**956**

mean gap and a Kolmogorov-Smirnov statistic. defense comparisons use a bootstrap whose unit we

**957**

state explicitly, since correlated prompts sharing a canary are not independent trials (106 resamples **958** for the configuration comparison of Table 15, 5 × 105 for the multi-seed replication of Table 16).

**959**

Every reported bound-shaped value is run through an automated entropy-cap audit (Appendix G.2).

**960 961**

E.2 EXPOSURE BY CANARY TYPE

**962**

**963** Two features of this table drive everything that follows. The mean exceeds the panel entropy, which **964** by Eq. (4) forces B∗ < 1 and makes the full-panel certificate vacuous at every budget. And the **965** type gradient spans two orders of magnitude (1.84 nats for T4 against 156.46 for T3), which is what **966** motivates type-stratified accounting. Both observations are correct as arithmetic. Whether either **967** reflects memorization is the question Section 6.3 settles.

**968**

| 969 | E.3 | POSITIVE CONTROL |
|---|---|---|
| 971 | Table 9 is the licence to read the rest of this section as evidence about models rather than about our implementation, and it is the control memorization audits most often omit. Three caveats bound what |  |

-----

| 973 974 |  | Table 9: Positive control. The pipeline that returns 0% on the 1.5B target recovers 10-16% from an over-memorized 7B checkpoint, so the 0% is a property of the model, not of the attack code. |  |
|---|---|---|---|
| 975 976 | Attack surface | 1.5B target | 7B over-memorized |
|  | W4 static templates | 0.00% | 10.3% |
| 977 | W4 adaptive (B=100) | 0.00% | 16% |
| 978 | W5 paraphrase (5 modes) | 0.00% | ≈8% |
| 979 980 | Final training loss | - | 0.044 |

**981**

**982** measured AUC chance = 0.5 0.6

---

**983**

**984** 0.55

---

0.52 **985** 0.5 0.5 0.5 ~~0.5~~ 0.5

---

**986**

0.45

**987** 0.45

---

**988**

0.4

---

**989**

All T1 T2 T3 T4

**990 991**

Figure 3: No canary type separates members from non-members. T2 scores below chance and T4 sits

**992**

exactly at it. Under a genuine memorization signal every bar would rise well above the dashed line. **993** Compare Figure 2: the type with the largest exposure (T3, 156 nats) achieves AUC 0.517.

**994 995**

**996** it supports. Its corpus is 700 documents against the target's 500K (Table 8), so it is a memorization **997** stress test, not a controlled scale comparison; the gap is consistent with model scale or training **998** intensity and we do not apportion between them. Neither the content filter nor LEAKCERT reduced **999** the 7B's extraction rate, which we flag as an unresolved anomaly, unexpected given both raise **1000** attacker cost on the 1.5B target. Finally, the per-canary output files for this run were lost to a

storage-configuration error, so the aggregates come from the run's recorded summary rather than raw

**1001**

output we can re-inspect; the configuration and launch scripts are released and the run is repeatable

**1002**

from the checkpoint (Appendix J).

**1003 1004**

**1005** E.4 CONTROL I: ADDITIONAL DETAIL

**1006**

**We audited for a pipeline defect and found none. Before accepting a null we checked the three**

**1007**

ways it could be an artifact. Panel independence: the generator gives each seed a private random

**1008**

stream for both secret value and context template, so seeds 42 and 999 generate disjoint secret sets, **1009** which we verified by explicit comparison of the two generated sets rather than inferring it from **1010** the seeding alone. Replay fidelity: the member panel is reconstructed with the exact injection-time **1011** parameters, and subset selection is deterministic and first-seen ordered, and we verified against the **1012** injection manifest that the replayed panel is a subset of what was injected. Injector cleanliness: **1013** canaries are added as independent documents and never modify existing ones, so the two corpora **1014** differ by exactly the canary documents. No defect was found; we accept the null as an experimental **1015** finding.

**1016 What this retracts. The claim that our target exhibits strong memorization (which Table 1 appears**

**1017** to support overwhelmingly) is not sustained. We are careful about direction: it is not that the model **1018** memorizes nothing, and not that exposure is useless in general. It is that a reference-model exposure **1019** score reported without a non-member panel does not license a memorization claim, even when the **1020** reference is correctly matched.

**1021**

| 1022 | E.5 | CONTROL II: ADDITIONAL DETAIL |
|---|---|---|
| 1024 1025 | Two things survive. Verbatim recovery is 0% on members and non-members alike, consistent with every other run. And the defense-cost signal is real, though it too is membership-blind: LEAKCERT |  |

forces 2.88 queries on T1 members against B1's 1.08, and a near-identical 3.00 on T1 non-members.

-----

| 1027 1028 1029 | Reference | Table 10: The null is reference-invariant. Training a reference on the identical corpus minus the canaries (the standard remedy for the fine-tuning-shift confound) does not recover separation. Corpus |  | AUC gap (nats) |
|---|---|---|---|---|
| 1030 | Base model | not fine-tuned | 0.49 | +0.001 |
| 1031 1032 | Matched (ours) | 500K docs, no canaries | 0.4855 | -0.0149 |

**1033**

members (TPR) non-members (FPR)

**1034**

---

**1035** 99 100

100 ~~90 93~~

88

---

**1036**

75

---

**1037**

**1038** 50

---

**1039**

25

---

**1040**

0

---

**1041**

B1 B5 LeakCert

**1042 1043**

Figure 4: The membership test's false-positive rate tracks its true-positive rate at every defense. A

**1044**

valid membership signal would show a large gap between the paired bars; here LEAKCERT even **1045** detects more non-members than members.

**1046 1047**

**1048** Its suppression stage raises the cost of the test regardless of what is being tested: a defense effect, not **1049** a memorization measurement. A corrected membership attack must score the secret's likelihood ratio **1050** calibrated against non-members, which is the quantity the exposure estimator computes and which

Section 6.3 shows to be at chance here.

**1051 1052**

| 1053 1054 | E.6 | CONTROL III: CAVEATS AND THE ONE HIT WE ROUNDED AWAY |
|---|---|---|
| 1055 1056 |  | W4 fires seven prompts per canary and W5 thirty-five, over only 100 distinct canaries; repeated probes of one secret are not independent evidence about more secrets. Two further caveats belong |

with these numbers. The superpopulation is the canary generator, not the prompt set: the interval is

**1057**

a statement about canaries drawn from G, and the prompt suite is a fixed benchmark rather than a

**1058**

sample, so the per-request row describes only the benchmark it was computed on. And the values are

**1059**

upper endpoints of two-sided 95% intervals; the corresponding one-sided 95% bounds are 0.427%,

**1060**

0.086%, and 2.951%. We report the two-sided endpoints for continuity with our earlier reporting and **1061** name the convention explicitly, since the two are often conflated. Both estimands are legitimate, but **1062** the prose around a 0% result ("the target does not leak its secrets") is a claim about secrets, and the **1063** per-canary bound is 6.9× and 34.4× larger than the two per-request figures. Both should be reported, **1064** with the per-canary figure carrying the headline.

**1065**

**The one hit we rounded away. A related habit is worth naming. Our sampled-decoding sweeps**

**1066**

report 0.00%, but one audit row did match: across the 12,600 audit rows of one run (100-canary panel; **1067** W4 and W5 prompts under all three defenses) exactly one row matched: a natural\_language- **1068** paraphrase prompt against the undefended target, i.e. one hit in the 3,500 undefended W5 prompts. **1069** Exact CP interval on that denominator: 0.029% [0.0007%, 0.159%]. On inspection we classify it as **1070** an incidental pattern match rather than a confirmed verbatim leak, and it did not reproduce under **1071** greedy decoding or under any defense. It remains one non-zero observation that a rounded 0.00% **1072** conceals.

**1073**

| 1074 1075 | E.7 | THE BUDGET DIAGNOSTIC IN FULL |
|---|---|---|
| 1076 1077 | Per Section 4, we do not claim the quantity below is a bound on I(K; Y B). What it is: B · κˆ, the expression a certificate of the form Eq. (2) would evaluate if the exposure statistic were a valid KL |  |
| 1078 1079 | estimate. Comparing it to the entropy ceiling answers a narrower but still useful question (is this panel even arithmetically capable of supporting a non-trivial bound, at any budget?), and the answer, |  |

shown in Figure 5, is almost always no.

-----

**1083**

**1084** 103

---

**1085**

**1086** 102

---

**1087**

101

---

**1088**

---

non-vacuous **1089** region (B ≤ 2)

100

---

**1090** 100 101 102 103 **1091** query budget B

**1092**

---

All (κ¯ˆ=19.99) T1 (17.53) T2 (11.13)

**1093**

T3 (156.46) **T4 (1.84)** *H(All)= 9.36* **1094** *H(T3/T4)= 5.65*

---

**1095**

**1096** Figure 5: Raw certificate vs. query budget, log-log. A certificate is informative only below its panel's **1097** entropy ceiling; we draw the two ceilings that bound the region of interest; T1's (9.210) lies just **1098** under the upper line and T2's (6.908) between the two. Every curve except T4 starts above its own **1099** ceiling already at B=1, so those certificates are vacuous at every budget. Only the weakly memorized

T4 panel enters the shaded region, and only for B ∈ {1, 2}: the single non-vacuous configuration in

**1100**

this study, matching the predicted crossover B∗ ≈ 3.

**1101 1102 1103**

**1104** Table 11: Full-panel budget diagnostic, both targets, base reference. Capped values equal H(K) **1105** everywhere.

**1106** Target *B Raw (nats)* Capped Vacuous

**1107**

102 2,429 9.356 yes

**1108**

103 24,294 9.356 yes **1109** 1.5B

| 104 | 242,941 | 9.356 | yes |
|---|---|---|---|
| 107 | 2.4 × 108 | 9.356 | yes |

**1111**

102 3,216 9.356 yes

**1112**

7B 104 321,552 9.356 yes **1113** 107 3.2 × 108

9.356 yes

**1114 1115 1116**

**1117 The full panel exceeds its ceiling before the first query. Because ¯** *κˆ = 19.99 > H(K) = 9.356,* **1118** Eq. (4) gives B∗ = 0.47 < 1. Table 11 confirms this across five decades of budget on both fine-tuned **1119** targets: after capping, the quantity equals H(K) everywhere, which is the trivial statement that an **1120** attacker learns at most the panel's entropy. The "tightness ratio of 1.0" the pipeline reports reflects **1121** two quantities both pinned to the cap and carries no information.

**1122 Type stratification yields one sub-ceiling cell. Table 1 applies Eq. (4) per type. Three of four types**

**1123** have B∗ < 1: their mean exposure alone exceeds their sub-panel entropy, so no budget helps. The **1124** T4 vulnerability panel (¯ *κˆ = 1.84, H = ln 283 = 5.645) is the exception, staying below its ceiling* **1125** at B ∈ {1, 2} (2.645 nats by the Hoeffding expression, 2.242 by Bernstein) and crossing at B=5,

matching B∗ ≈ 3.06.

**1126**

**1127** We deliberately do not convert this into an extraction-probability statement. Doing so requires **1128** Fano's inequality over a local candidate set in which exactly one of κ structurally identical strings **1129** was injected; our 283 T4 canaries are all members occupying different slots, so the conversion we **1130** previously reported was mis-specified and is withdrawn (Section 4.3). Nor is the cell evidence about **1131** memorization: T4's member/non-member AUC is exactly 0.500 (Figure 3). What the row shows is **1132** narrower and still worth stating: the only panel arithmetically capable of supporting a non-trivial **1133** bound is the one the model barely memorized, which is the opposite of where an auditor would want

a guarantee.

-----

| 1135 1136 |  | column is the analytic Rényi composition bound, as no per-ϵ DP checkpoint completed training. | Table 12: Analytic comparison at B=104 (1.5B, full panel). Both quantities cap at H(K); the DP |  |
|---|---|---|---|---|
| 1137 1138 | DP ϵ | LEAKCERT capped | Raw DP bound | DP capped |
|  | 1 | 9.4 | 5,000 | 9.4 |
| 1139 | 2 | 9.4 | 20,000 | 9.4 |
| 1140 | 4 | 9.4 | 80,000 | 9.4 |
| 1141 | 8 16 | 9.4 9.4 | 320,000 1.28 × 106 | 9.4 9.4 |

**1142**

---

**1143 1144**

**1145** Table 13: W3 utility on the 1.5B target (HumanEval, 164 problems, pass@1, identical checkpoint, **1146** most recent run). Absolute pass@1 is low because the target is a small non-instruction-tuned base **1147** fine-tuned on a canary-injected corpus; an earlier run of the same configuration reorders the arms

(see text), so no ordering should be inferred.

**1148**

| 1149 | Defense | pass@1 | correct/164 | refusal |
|---|---|---|---|---|
| 1150 | B1 no defense | 6.1% | 10 | 0.0% |
| 1151 | B2 temperature 0.5 | 4.3% | 7 | 0.0% |
| 1152 | B3 top-p 0.7 | 6.7% | 11 | 0.0% |
|  | B5 content filter | 4.3% | 7 | 0.0% |

**1153**

LEAKCERT 6.1% 10 0.0%

**1154**

---

**1155 1156**

**Prior sensitivity and the analytic DP comparison.** Replacing the uniform prior with the empirical

**1157**

type prior (Section 4.1) moves H(K) from 9.356 to 9.250 nats and the capped certificate from 9.4 to

**1158**

9.3; both remain at the cap, so prior information helps through stratification rather than the global

**1159**

entropy correction. Table 12 compares our quantity to the analytic Rényi composition bound Bϵ2/2 **1160** at B=104. Both exceed H(K) and cap: on this target, neither an empirical exposure accounting nor **1161** an analytic DP promise at these ϵ values says anything non-trivial. No DP checkpoint was trained, so **1162** the DP column is analytic only.

**1163 1164**

E.8 UTILITY, REFUSAL, AND OVERHEAD

**1165 1166**

Table 13 reports HumanEval pass@1 on the 1.5B target with the identical checkpoint under every

**1167**

defense. LEAKCERT matches the undefended baseline at 6.1% (10/164) with a 0% refusal rate. We

**1168**

caution against reading the ordering: an earlier run of the same defenses on the same checkpoint **1169** reports 5.5/8.5/4.9/4.9/6.7%, reordering the arms entirely. The spread across defenses (4.3-8.5% **1170** across both runs) is sampling noise at n=164 with one sample per problem, which is precisely why **1171** we decline the equivalence claim. A matched diagnostic on the leaky 0.5B checkpoint puts B1, B5, **1172** and LEAKCERT at an identical 10.98% (18/164) with LEAKCERT refusing 0.61%, and an error **1173** breakdown attributes the dominant failure mode identically across defenses (AssertionError, **1174** 40 of 164 in all three arms), confirming the defense layer is not the bottleneck. Per Observation 3 we **1175** read this as no detected difference at low power, not equivalence.

**1176 The refusal threshold has a sharp knee. Figure 6 sweeps the learned-refusal threshold. Below t=0.9**

**1177** the classifier refuses a large fraction of legitimate completions (45% at t=0.7, which costs almost **1178** all utility), while t ≥ 0.95 holds refusals at or below 2.5% with pass@1 at its plateau. This is what **1179** selects t=0.95 as the operating point, and it is the clearest instance in our data of the utility-leakage **1180** tension that we declined to state as a theorem (Section 4.3).

**1181**

**1182 Overhead. The monitor is not deployable as evaluated. Median per-decision latency on the 1.5B**

**1183** target is 52 s in the most recent run and 80 s in an earlier one, dominated by the reference-model **1184** forward pass the exposure stage requires. On the leaky 0.5B checkpoint the learned-only variant at **1185** *t=0.95 measures 12.0 s median / 14.5 s p99 over the 80-problem threshold sweep, but 19.1 s / 28.9 s* **1186** and 32.8 s / 39.5 s in two runs over the full 164 problems; we quote the range rather than the most

favourable figure, since the spread is 2.7× and we cannot attribute it to configuration. We therefore characterize LEAKCERT as an offline audit monitor; reaching interactive latency (by caching per-key

-----

refusal rate

**1189** 40

---

pass@1

**1191**

**1192** 20

---

**1193 1194**

0

---

**1195** 0.7 0.8 0.9 0.95 0.98 **1196** refusal threshold t

**1197**

**1198** Figure 6: Refusal-threshold sweep on 80 HumanEval problems. Aggressive thresholds destroy utility

by refusing legitimate completions; t=0.95 is the knee, holding refusals at 2.5% with pass@1 at

**1199**

plateau.

**1200 1201 1202**

running exposure, or decoupling certificate updates from the request path) is future work, not a claim

**1203**

of this paper.

**1204 1205**

E.9 CREDENTIAL-EXTRACTION WORKLOAD

**1206**

**1207** On the full 4,832-prompt credential-extraction benchmark, run on the leaky 0.5B checkpoint, no **1208** configuration extracted any controlled ground-truth secret (zero hits under B1, B5, and LEAKCERT; **1209** LEAKCERT refusal 0.08%). We report this as an operational negative control establishing that the **1210** benchmark and scorer path work end to end, not as a reproduction of the findings of (Huang et al., **1211** 2024), whose user-level artifacts were never released. A three-example public supplementary probe **1212** over AWS and Slack credential formats likewise returned 0/3 under all six defenses.

**1213**

## 1214 F LIMITATIONS

**1215 1216**

**One training run is the binding limitation. The member/non-member analysis scores 1,132**

**1217** canaries per side, but all come from a single target/reference training pair. They are not 2,264 **1218** independent observations of the training phenomenon: the natural hierarchy is training seed → **1219** template → canary → prompt, and the relevant independent unit for generalizing about fine-tuning **1220** is the training run. Accordingly, the intervals in Table 4 characterize within-run uncertainty and **1221** understate across-training variability. Establishing generality requires multiple independently trained **1222** target/reference pairs with cluster-aware or mixed-effects inference.

**1223 Limited injection regime and panel design. Our central null result covers one model scale, one**

**1224** injection regime (each canary inserted once over three epochs), and one panel structure. It does **1225** not imply that the target memorizes nothing. A repetition sweep would be needed to determine the **1226** estimator's detection floor. Moreover, heavy template reuse may induce format-level generalization **1227** that raises both member and non-member scores. We did not characterize template counts or evaluate **1228** template-disjoint non-members and per-slot near-neighbour decoys, so we cannot determine whether **1229** the null is specific to this panel design or general to reference-ratio audits.

**1230 Positive-control and cross-arm confounds. The over-memorized 7B arm is trained on only 700**

**1231** documents versus 500K for the primary target, so it validates the extraction pipeline but does not **1232** isolate model scale from training intensity. Its per-canary artifacts were also lost. More importantly, **1233** this positive control applies only to extraction: we did not evaluate member/non-member exposure **1234** separation or the membership test's TPR-FPR gap on that checkpoint. Each instrument therefore still **1235** needs its own positive control, ideally through a repetition sweep that holds architecture and corpus

fixed.

**1236**

**1237 Theoretical and access limitations. The concentration expressions reported in Appendix D are not**

**1238** valid certificates because canary scores are dependent through shared training and templates, the **1239** range parameter is estimated from the observed sample, and the Bernstein form omits its range term. **1240** The likelihood-based audit also requires log-probability access (Section 3); we provide neither a **1241** sample-only estimator nor its sample complexity. The method is therefore not directly applicable to

text-only completion APIs.

-----

**Extraction coverage and attack strength. Extraction is scored primarily by exact string match.**

**1243** Semantic or behavioural leakage from T2-T4 may therefore go undetected; semantic, AST-level, **1244** or vulnerability-pattern scorers would provide a broader measure. Our adaptive attacker is also **1245** budget-limited: runs beyond B=100 exceeded wall-clock limits, and two defended adaptive cells **1246** did not complete. Stronger decoding and prompt-search strategies could surface leakage that our **1247** evaluation misses.

**1248**

**Defense evaluation. defense efficacy is evaluated on the leaky 0.5B arm rather than the primary**

**1249** target. The refusal classifier's training and evaluation data are not fully disjoint, the threshold was **1250** selected on a HumanEval subset overlapping utility evaluation, and prompt-level bootstrap intervals **1251** are optimistic because prompts sharing a canary are correlated. A nested tune-freeze-evaluate **1252** protocol with canary-level resampling is needed before interpreting the observed improvements as **1253** out-of-sample. We also include no trained DP baseline.

**1254 Utility and deployability. Utility is measured with one sample on each of 164 HumanEval problems**

**1255** at low pass@1, which is insufficient for an equivalence or non-inferiority claim. Finally, the monitor **1256** requires approximately 52-80 s per decision in our evaluation and should therefore be viewed as an **1257** offline audit tool rather than an inline defense.

**1258 1259**

## G SUPPLEMENTARY DETAIL

**1260 1261**

G.1 EXPOSURE ESTIMATOR

**1262**

**1263** For canary ki with context ci,

**1264**

**1265** *κˆi = log pθ(ki | ci) - log pref(ki | ci),*

**1266**

computed by teacher forcing over the secret's token span under both models and summing per-token **1267** log-probabilities. Negative values are clamped to zero before aggregation; the raw signed statistic **1268** is retained for the member/non-member comparison of Table 4, where clamping would destroy **1269** the very comparison at issue. This is why the means in that table (≈ 49 nats, signed, matched **1270** reference, n=1,132) are on a different scale from those in Table 1 (19.99 nats, clamped, base **1271** reference, n=11,566); both are correct for their stated configuration.

**1272**

A per-instance κˆ i may numerically exceed H(K) without contradiction: it is a single-instance statistic, **1273** whereas the entropy bound constrains the aggregate population mutual information. Conflating the **1274** two produced the earlier, incorrect assertion that a single completion could carry more information **1275** than the panel's entire mutual information. The entropy cap therefore belongs at the aggregate level, **1276** after averaging, not on individual scores. We report the panel maximum (284.08 nats) uncapped and **1277** exclude it from the aggregated quantity.

**1278**

| 1279 1280 | G.2 | ENTROPY-CAP AUDIT |
|---|---|---|
| 1281 | Every certificate and mutual-information value passes an automated audit flagging any raw value exceeding H(K). Applied retrospectively across 23 historical result files from our own earlier runs, |  |

**1282**

the audit checked 155 values and flagged 108 as exceeding the ceiling; 14 of 23 files failed outright

**1283**

(four passed; five lacked a recorded H(K)). Those raw values are retained only as diagnostics, and

**1284**

all reader-facing quantities are capped. We recommend reporting the triple (raw, capped, vacuity flag)

**1285**

as default, since a capped value alone hides how far the raw bound overshot, in our tables, by up to

**1286**

seven orders of magnitude (Table 11).

**1287 1288**

G.3 INFORMATIVE-BUDGET DIAGNOSTIC

**1289**

**1290** As a sanity check on the vacuity machinery we ran the budget sweep on two additional exposure **1291** sources over a 392-canary panel (H = 5.971 nats). A high-exposure diagnostic source saturates **1292** the cap at every budget from B=1 to B=2000, with B/B∗ ranging from 30.8 to 6.2 × 104 , i.e. **1293** overshooting the non-vacuity threshold by one and a half to nearly five orders of magnitude. A **1294** zero-exposure control source yields a certificate of exactly 0.000 nats at every budget, confirming **1295** the non-vacuous path is reachable when the estimated exposure is genuinely zero. Neither is a

memorization result; both verify that the cap and the vacuity flag behave as specified.

-----

**1297** Table 14: Cross-seed baselines (leaky 0.5B arm, mean of seeds 42-43). Sampling controls do not **1298** help.

| 1299 | Defense | W4 |  | W5 W5/W4 |
|---|---|---|---|---|
| 1300 | B1 no defense | 9.38% | 8.12% | 0.861 |
| 1301 | B2 temperature 0.5 | 12.95% | 10.27% | 0.793 |
| 1302 | B3 top-p 0.7 | 13.17% | 9.51% | 0.721 |
| 1303 | B5 content filter LEAKCERT (full) | 11.38% 9.16% | 6.70% 7.00% | 0.586 0.764 |

**1304**

---

**1305 1306**

G.4 CLOPPER-PEARSON COMPUTATION

**1307**

**1308** Intervals in Table 3 are exact Clopper-Pearson bounds obtained by bisection on the binomial CDF. **1309** For zero successes the upper bound reduces to 1 - (α/2)1/n , which we use as a closed-form check: **1310** *n=700 ⇒ 0.5256%; n=3,500 ⇒ 0.1053%; n=100 ⇒ 3.6217%. For the single sampled-decoding* **1311** hit, x=1, n=3,500 gives 0.029% [0.0007%, 0.159%]. The routine is released so the estimand **1312** distinction can be re-derived independently.

**1313**

**1314** G.5 PANEL CONSTRUCTION AND DISJOINTNESS

**1315**

The generator assigns each seed a private pseudo-random stream from which both the secret value

**1316**

and the context template are drawn, so panels built with seeds 42 and 999 have disjoint secret sets

**1317**

(verified by explicit set comparison, not inferred from the seeding) while sharing format, context

**1318**

distribution, and character classes. Stratified subset selection is deterministic in first-seen order, so

**1319**

a replayed member panel built with injection-time parameters is a subset of the injected set, which **1320** we verified against the injection manifest. The corpus injector inserts each canary as an independent **1321** additional document at a random position and never modifies existing documents, so the matched **1322** reference corpus differs from the target corpus by exactly the canary documents.

**1323**

| 1324 1325 | G.6 | CROSS-SEED BASELINES |
|---|---|---|
| 1326 1327 | Table 14 reports the sampling-control baselines on the leaky 0.5B arm, averaged over seeds 42-43. Neither temperature nor top-p reduces extraction relative to no defense in this setting: both increase |  |

it, consistent with sampling controls trading diversity for mode-seeking behaviour that favours

**1328**

memorized continuations. Only the content filter and the learned refusal variant reduce it.

**1329 1330**

## 1331 H DEFENSE EVALUATION IN FULL

**1332**

**1333** This appendix gives the complete defense evaluation summarised in Section 6.6. All results are on **1334** the leaky 0.5B checkpoint; none of them is a memorization-defense result, for the reasons Section 6.6 **1335** states and Appendix H.5 quantifies.

**1336**

**1337** H.1 THE LEAKCERT RUNTIME MONITOR

**1338**

Figure 7 shows the four-stage monitor that accompanies the audit: a certificate-budget throttle, a

**1339**

per-key rate limiter, an uncertainty-refusal classifier, and regex/hash suppression. We evaluate four

**1340**

configurations: full (all four stages), calibrated-aggressive, calibrated-softheuristic at t=0.95, and

**1341**

*learned-only at t=0.95 (uncertainty refusal alone). They are compared with B1 (no defense), B2* **1342** (temperature 0.5), B3 (top-p 0.7), and B5 (content filter: a regex bank, Meli et al., 2019, plus a **1343** learned secret classifier, Saha et al., 2020).

**1344**

| 1345 1346 | H.2 | MONITOR CONFIGURATIONS |
|---|---|---|
| 1347 1348 | Table 15 compares four LEAKCERT configurations against the content filter under a 106 -resample bootstrap. This is a result we would have preferred to omit and consider important to report: the full |  |
| 1349 | monitor (the configuration the architecture of Figure 7 describes) does not beat the content filter, and | neither does the soft-heuristic calibration. Only the two learned variants do. |

-----

![](img_p26_1.png)

**1353 1354 1355 1356 1357 1358 1359 1360 1361 1362 1363 1364 1365 1366 1367 1368 1369 1370 1371 1372 1373 1374 1375 1376 1377 1378 1379 1380**

---

**1381 1382 1383**

---

**1384 1385 1386 1387 1388 1389 1390 1391 1392 1393 1394 1395 1396 1397 1398 1399 1400**

Figure 7: The four-stage monitor: certificate-budget throttle, per-key rate limiter, uncertainty-refusal classifier, and regex/hash suppression. We evaluate it as an offline audit tool; decisions are computed and logged, not served inline (Section 6.6).

Table 15: Monitor configurations vs. the B5 content filter on W5 paraphrase extraction (106 -resample bootstrap). Two of four configurations fail to beat the baseline; the full monitor is one of them.

| Configuration | Seed | B5 | Variant | P(B5>·) |
|---|---|---|---|---|
| Full monitor | 43 | 5.71% | 5.89% | 0.410 |
| Full monitor | 42 | 7.68% | 8.13% | 0.333 |
| Calib. soft-heuristic | 43 | 5.71% | 6.43% | 0.226 |
| Calib. aggressive | 43 | 5.71% | 2.32% | 0.99998 |
| Learned-only t=0.95 | 43 | 5.71% | 2.50% | 0.99993 |
| Learned-only t=0.95 | 42 | 7.68% | 4.73% | 0.99787 |

H.3 MULTI-SEED REPLICATION

Figure 8 and Table 16 give the replication. The direction holds in every seed, with an aggregate reduction from 5.98% to 2.84% over 5,600 paired prompts.

H.4 PER-PARAPHRASE-MODE BREAKDOWN Figure 9 breaks W5 down by the five rewriting modes. The content filter is roughly flat across modes at 4.6-6.3%, consistent with a lexical defense that each mode evades about equally; the learned variant reduces every mode, most strongly on natural-language descriptions (5.51% → 1.04%), which are the furthest from any regex the filter encodes.

H.5 COMPONENT ABLATION Table 17 removes one monitor stage at a time on two panels. The panels disagree about which output-side stage matters: on the larger panel removing the rate limiter raises W5 extraction from 0.00% to 4.46% while removing refusal leaves W5 at 0.00%; on the smaller panel the pattern reverses: and we report both rather than the more convenient one. What both agree on is the finding that matters for this paper's thesis: removing certificate accounting changes nothing on either panel, in either workload. We have no experiment in which certificate accounting alters a security decision the

-----

B5 content filter LEAKCERT learned-only

---

**1406** 10

---

**1407 1408**

**1409** 5

---

**1410 1411**

**1412** 0

---

42 43 44 45 46 47 48

**1413**

seed

**1414 1415 1416 1417 1418 1419 1420 1421**

---

**1422**

---

**1423 1424 1425 1426 1427 1428 1429**

---

**1430**

---

Figure 8: Paraphrase (W5) extraction across seven seeds. The learned-only refusal variant is below the content filter in every seed. Seeds 47-48 use a smaller panel (Table 16).

Table 16: W5 extraction, B5 vs. learned-only LEAKCERT. Seeds 42-46 use 1,120 W5 prompts each; 47-48 use 560. Rates and ∆ in percent / percentage points. Bootstrap intervals resample prompts and are therefore optimistic (Appendix F).

| Seed | B5 | LEAKCERT | ∆ | 95% CI | P |
|---|---|---|---|---|---|
| 42 | 7.68 | 4.73 | 2.95 | [0.98, 4.91] | 0.998 |
| 43 | 5.71 | 2.50 | 3.21 | [1.61, 4.82] | 1.000 |
| 44 | 5.80 | 2.68 | 3.13 | [1.52, 4.82] | 1.000 |
| 45 | 6.61 | 2.77 | 3.84 | [2.14, 5.63] | 1.000 |
| 46 | 4.11 | 1.52 | 2.59 | [1.25, 3.93] | 1.000 |
| 47 | 9.46 | 3.57 | 5.89 | - | - |
| 48 | 4.11 | 0.54 | 3.57 | - | - |
| Agg. 42-46 | 5.98 | 2.84 | 3.14 | [2.39, 3.91] | 1.000 |

**1431 1432**

other stages would not have made, and we do not claim one. The defense evidence here supports

**1433**

output-side mechanisms, not the certificate architecture that motivates them.

**1434**

**1435**

H.6 ALL MEASURED EXTRACTION IS VULNERABILITY CANARIES

**1436 1437**

A per-type breakdown of the same ablation reveals something the aggregate rates hide: in every **1438** configuration, T1 literal, T2 paraphrase, and T3 semantic extraction are exactly 0.00%, and the entire **1439** aggregate is carried by T4 vulnerability canaries: 50.0% under B5 and 25.0% under LEAKCERT **1440** on Panel A's W4. Since T4 canaries are short insecure-code idioms (string-concatenated SQL, **1441** disabled host-key checking) that a code model has ample reason to emit without having memorized **1442** any particular instance, we caution that this arm measures suppression of vulnerability-pattern **1443** *generation rather than recovery of planted secrets. The defense result is real and replicated; its* **1444** security interpretation is narrower than "prevents secret extraction."

**1445**

## 1446 I ETHICS CONSIDERATIONS

**1447**

**1448** We assessed this work against the Menlo Report principles. No real user data, live credential, or **1449** third-party secret was created, handled, or placed at risk.

**1450**

**1451 Synthetic canaries only.** Every canary is synthetic. Credential-shaped canaries imitate the format **1452** of real credential types (so that the audit is realistic) but their key bodies are randomly generated **1453** and correspond to no issued credential: JWTs are signed by a research-only key, RSA fragments **1454** were generated for the panel and never used, and licence keys follow an invented vendor scheme. **1455** No canary is or has been valid for any account, service, or person, and none was obtained from any **1456** real repository. Canaries are tagged in the corpus and excluded from utility evaluation. Because the **1457** strings deliberately resemble credentials, we exclude raw benchmark files from the released package

(they would trigger secret-scanning systems) and ship deterministic regeneration scripts instead.

-----

B5 content filter LEAKCERT learned-only

---

8

---

**1460**

6.25 **1461** 6 ~~5.51~~ 5.66 ~~5.51~~

---

**1462** 4.61

**1463**

---

2.68 2.83

2.53 2.53

**1464**

2

---

1.04

**1465**

**1466** 0

---

**1467**

**1468**

**1469** Figure 9: W5 extraction by paraphrase mode, mean over seeds 44-46. The learned variant reduces **1470** every mode; the largest gap is on natural-language descriptions, the mode least reachable by a regex **1471** bank.

**1472**

**1473** Table 17: Component ablation on two panels (Panel A: 224 W4 / 1,120 W5; Panel B: 112 / 560). The **1474** panels disagree on rate limiting vs. refusal; both agree that removing certificate accounting has no **1475** effect.

| 1476 |  | Panel A |  | Panel B |  |
|---|---|---|---|---|---|
| 1477 1478 | Variant | W4 | W5 | W4 | W5 |
| 1479 | B5 content filter LEAKCERT full | 12.50 6.25 | 10.71 0.00 | 12.50 6.25 | 12.32 6.07 |
| 1480 | - rate limiter | 6.25 | 4.46 | 6.25 | 6.07 |
| 1481 | - cert. accounting | 6.25 | 0.00 | 6.25 | 6.07 |
| 1482 | - suppression - learned refusal | 6.25 12.50 | 0.00 0.00 | 6.25 12.50 | 6.07 12.32 |

**1483 1484**

**1485**

**No real user data in the credential-extraction workload.** The extraction artifacts of Huang et al.

**1486**

(2024) contain real user-level data and were withheld by their authors on privacy grounds. We did not

**1487**

attempt to reconstruct them. Our comparable benchmark is fully synthetic and every row is marked **1488** as containing no real PII. A separate public-supplementary probe used only three already-public **1489** examples.

**1490**

| 1491 1492 | Vulnerability canaries. | T4 canaries are insecure coding patterns (string-concatenated SQL, dis- abled host-key verification, unsafe deserialization). They are short, widely documented anti-patterns |
|---|---|---|
| 1493 1494 | no working exploit. | rather than exploits, and we report them to study whether models reproduce insecure style; we publish |

**1495**

| 1496 | Attack code and dual use. | The attacks we implement (template, divergence, paraphrase, perplexity- |
|---|---|---|
| 1497 | ranked, and likelihood-ratio) | are established in the literature; we introduce no new extraction capa- |

bility, and our strongest attacker requires knowledge of the canary set, which deployed adversaries

**1498**

lack. This paper's principal offensive-side findings are negative: a widely available membership test

**1499**

is invalid, and a widely used exposure statistic does not evidence memorization without a control.

**1500**

Publishing them reduces rather than increases attacker capability and protects practitioners from

**1501**

acting on flawed audit evidence.

**1502**

**1503 1504 1505**

**Human subjects. No human subjects, human-derived data, or user studies are involved; no IRB**

review was required.

| 1506 1507 | Reporting of corrected and retracted claims. | This paper retracts three empirical findings and five theoretical claims we previously held, reports that two of four of our own monitor configurations fail |
|---|---|---|
| 1508 1509 |  | to beat a regex baseline, reports that our certificate-accounting stage contributes nothing measurable by ablation, and reports one finding (defenses failing on the 7B arm) as unresolved rather than |
| 1510 1511 |  | omitting it. We regard surfacing such results as an obligation of security measurement work, and we have tried to state the direction of each negative result precisely so that it is not read as a stronger |

claim than the evidence supports.

-----

**Use of AI tools.** Our disclosure of generative AI use, as required by the ICLR 2027 AI Policy for **1513** Authors, is given in the AI use statement preceding the references.

**1515**

## J ARTIFACT AVAILABILITY AND OPEN SCIENCE

**1516 1517**

The artifact accompanying this submission is available to reviewers as a frozen, anonymous, tracking-

**1518**

[free archive at https://anonymous.4open.science/r/LeakCert-42AC/README.](https://anonymous.4open.science/r/LeakCert-42AC/README.md)

**1519**

md (no login, no analytics, no author-identifying metadata). The same contents are mirrored in

**1520**

the supplementary-material upload. Upon acceptance we will publish the repository and mint a DOI. **1521** Every file in the archive is listed with its SHA-256 digest in MANIFEST.sha256, and every table **1522** and figure in this paper names the artifact file it was generated from.

**1523**

**1524 What we release.** (i) The complete LEAKCERT pipeline: canary generation and injection, the **1525** exposure/LLR estimator, certificate computation with its entropy-cap audit, the four-stage runtime **1526** monitor, and all attack implementations including the false-positive control harness. (ii) Training **1527** and evaluation configurations for every arm in Table 8, with fixed seeds. (iii) Per-run JSON artifacts **1528** backing each table and figure, with SHA-256 manifests, including the member and non-member **1529** exposure distributions behind Table 4 and Figure 3, the SPRT member/non-member results of Table 5,

the full budget sweep behind Figure 5, the seven-seed W5 results of Table 16, both component

**1530**

ablations of Table 17, and the threshold sweep of Figure 6. (iv) The exact Clopper-Pearson routine

**1531**

used for Table 3, so the estimand distinction can be re-derived independently. (v) The credential-

**1532**

extraction benchmark generator.

**1533 1534**

**Reproducing the central result.** The negative result of Section 6.3 is reproducible without retrain-

**1535**

ing: given the released target checkpoint, the matched reference checkpoint, and the seed-42/seed-999 **1536** panel generators, recomputing the member and non-member exposure distributions and their AUC **1537** is a few GPU-hours of inference. We consider this the artifact a reviewer should run first, and we **1538** provide a single entry point for it.

**1539**

**1540 What we cannot release, and why. Raw canary files are withheld because they are designed to**

**1541** resemble credentials and would trigger secret-scanning systems; deterministic regeneration scripts **1542** with the original seeds are provided instead and produce byte-identical panels. Model checkpoints **1543** are large (the 1.5B target and its matched reference are ≈ 3 GB each). Because regenerating the

matched reference costs ≈ 173 GPU-hours, checkpoint availability (not code availability) is the

**1544**

binding constraint on reproducing our central result, so we commit to hosting both checkpoints

**1545**

on a research-data repository with per-file SHA-256 digests rather than treating this as best-effort.

**1546**

Training scripts, corpus manifests, seeds, and step counts are included regardless.

**1547 1548**

**Known artifact gaps.** Two artifacts referenced in this paper were lost to a storage-configuration

**1549**

error and are not recoverable: the per-canary and per-defense output files for the 7B run of Table 9 **1550** (which is why the defense anomaly in Section 6.2 is reported as unresolved, and why that row is **1551** backed by the run's recorded aggregate figures and its configuration rather than by raw per-canary **1552** output) and the raw log for one large sampled-decoding sweep. The 7B evaluation configuration **1553** and launch scripts are released, so the run is repeatable from the checkpoint even though its original **1554** outputs are not archived. Where this affects a claim, we restate the claim on a smaller sweep whose **1555** artifacts survive and which we do release (Section 6.5). We flag these gaps rather than quoting **1556** numbers we cannot back with a checkable artifact.

**1557 1558 1559 1560 1561**