#!/usr/bin/awk -f
# Exact two-sided Clopper-Pearson 95% CI for a Binomial(n, p) count.
#
# Usage: awk -f compute_cp_ci.awk -v x=0 -v n=700
#   x = number of successes (extraction hits)
#   n = number of trials
#   alpha = significance level (default 0.05 -> 95% CI)
#
# Method: bisection on the exact binomial CDF (no incomplete-beta / lgamma
# dependency, so it runs under plain awk/gawk/mawk). For the upper bound we
# solve P(X <= x | n, p) = alpha/2 for p; for the lower bound we solve
# P(X >= x | n, p) = alpha/2, i.e. P(X <= x-1 | n, p) = 1 - alpha/2.
# Binomial CDF is evaluated via the log-space recurrence
#   term(0)   = exp(n * log(1-p))
#   term(k+1) = term(k) * (n-k)/(k+1) * p/(1-p)
# which avoids factorials/lgamma entirely and is numerically stable for the
# n used here (up to ~1.5e5).

function safe_exp(z) {
    if (z < -700) return 0.0   # underflows double anyway; avoid libm range warnings
    return exp(z)
}

function binom_cdf(k, n, p,    term, cdf, i) {
    if (p <= 0) return (k >= 0) ? 1.0 : 0.0
    if (p >= 1) return (k >= n) ? 1.0 : 0.0
    term = safe_exp(n * log(1 - p))
    cdf = term
    for (i = 0; i < k; i++) {
        term = term * (n - i) / (i + 1) * p / (1 - p)
        cdf += term
    }
    return cdf
}

# Solve binom_cdf(k, n, p) = target for p via bisection on [lo, hi].
# increasing=1 means binom_cdf(k,n,p) is decreasing in p (true: CDF at fixed k
# is a decreasing function of p), so we bisect accordingly.
function solve_p(k, n, target,    lo, hi, mid, val, iter) {
    lo = 0.0; hi = 1.0
    for (iter = 0; iter < 100; iter++) {
        mid = (lo + hi) / 2
        val = binom_cdf(k, n, mid)
        # val decreases as mid increases
        if (val > target) lo = mid; else hi = mid
    }
    return (lo + hi) / 2
}

BEGIN {
    if (alpha == "") alpha = 0.05
    if (n == "" ) { print "usage: awk -f compute_cp_ci.awk -v x=<hits> -v n=<trials> [-v alpha=0.05]"; exit 1 }

    if (x == 0) {
        lower = 0.0
    } else {
        lower = solve_p(x - 1, n, 1 - alpha/2)
    }
    if (x == n) {
        upper = 1.0
    } else {
        upper = solve_p(x, n, alpha/2)
    }

    printf "x=%d n=%d alpha=%.3f  point=%.6f%%  CI=[%.6f%%, %.6f%%]\n", \
        x, n, alpha, 100*x/n, 100*lower, 100*upper
}
