from contextlib import contextmanager

from . import _state
from .patch import patch

__version__ = '0.1.0'


@contextmanager
def disabled():
    """Run the plain DRF implementation inside the block (useful for comparisons and debugging)."""
    previous = _state.enabled
    _state.enabled = False
    try:
        yield
    finally:
        _state.enabled = previous


__all__ = ['disabled', 'patch']
