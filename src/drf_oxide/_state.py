import os

# Global switch, see `drf_oxide.disabled()`.
enabled = True

# Re-raise compilation errors instead of silently using DRF (`DRF_OXIDE_STRICT=1`, the test suite).
strict = os.environ.get('DRF_OXIDE_STRICT') == '1'
