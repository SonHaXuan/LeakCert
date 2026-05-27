"""
LeakCert: Extraction-Resistant Code Completion with Information Leakage Certificates.

Framework overview:
  - canary/       : T1-T4 canary generation and corpus injection
  - model/        : model backend completion service + fine-tuner (standard + DP-SGD)
  - certificate/  : KL estimation + Theorems 5, 7, 10, 13, 17
  - runtime/      : Online release monitor (rate limiter, refusal, suppression)
  - attacks/      : A-fixed, A-grid, A-adaptive, A-greedy-LRT
  - defenses/     : B1-B8 baselines
  - evaluation/   : W1-W5 workloads, metrics, experiment runner
"""

__version__ = "0.1.0"
