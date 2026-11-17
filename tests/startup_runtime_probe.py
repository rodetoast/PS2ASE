"""Optional runtime hook for isolated validation builds only, never release spec."""
import os
import time
import json
import sys
import types

_probe_path = os.environ.get("ASEPS_STARTUP_PROBE")
if _probe_path:
    with open(_probe_path, "a", encoding="utf-8") as _probe:
        _probe.write(json.dumps({"event": "runtime_hook", "wall": time.time(),
                                 "perf": time.perf_counter()}) + "\n")

# Only this private control-build hook supports suppressing both splash paths.
if os.environ.get("ASEPS_VALIDATION_NO_SPLASH") == "1":
    module = types.ModuleType("pyi_splash")
    module.is_alive = lambda: True
    module.close = lambda: None
    sys.modules["pyi_splash"] = module
