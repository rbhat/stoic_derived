"""SP5 static-dashboard JSON/control API.

The package never renders application HTML.  The React/Vite application lives
in ``web/`` and consumes only the versioned API contracts exported here.
"""

from .app import create_app
from .settings import DashboardSettings

__all__ = ["DashboardSettings", "create_app"]
