"""Finite experiment ownership bounds shared by stop, drain and recovery."""

MAX_COMPARISON_TRIALS = 4 * 4000  # three tuning comparisons and one selected final
MAX_PREPARATION_TRIALS = 2000
MAX_TRIALS = MAX_COMPARISON_TRIALS + MAX_PREPARATION_TRIALS
MAX_ATTEMPTS_PER_TRIAL = 2
MAX_TRIAL_ATTEMPTS = MAX_TRIALS * MAX_ATTEMPTS_PER_TRIAL
MAX_ROLE_OPERATIONS = 1 + 1 + 1 + 3  # proposer, one repair, one compose, three candidate reviewers
MAX_ROLE_ATTEMPTS = MAX_ROLE_OPERATIONS * 2
