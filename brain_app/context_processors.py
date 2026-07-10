from pathlib import Path
import json
import sys

# Ensure views can be imported
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

def bundle_root_processor(request):
    from brain_app.views import get_bundle_root
    return {
        'bundle_root': get_bundle_root(request)
    }
