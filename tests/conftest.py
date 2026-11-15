import importlib.metadata
import os
import sys

import werkzeug

# the app lives one folder up
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Flask 2.3's test client reads werkzeug.__version__, which Werkzeug 3 (what
# the unpinned requirement installs) no longer has. Test-only.
if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = importlib.metadata.version("werkzeug")
