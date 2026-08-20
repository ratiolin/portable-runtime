"""Provider-independent runtime primitives.

The existing :mod:`control_plane` package remains available as the legacy
profile.  This package is the stable seam for new integrations.
"""

from .core.runtime import Runtime

__all__ = ["Runtime"]
__version__ = "0.1.0"
