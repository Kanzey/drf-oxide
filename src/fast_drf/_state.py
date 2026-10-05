import os

# Global switch, see `fast_drf.disabled()`.
enabled = True

# Re-raise compilation errors instead of silently using DRF (`FAST_DRF_STRICT=1`, the test suite).
strict = os.environ.get('FAST_DRF_STRICT') == '1'
