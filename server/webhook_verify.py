"""webhook_verify.py - kept for older imports: the provider profiles live in webhook_auth.py (spec §13)."""
from webhook_auth import (ADAPTER_STATUS, PROVIDERS, STRIPE_TOLERANCE_S, SYSTEME_IO, VerifyError,  # noqa: F401
                          idem_key, normalize, validate, verify, verify_ex)
