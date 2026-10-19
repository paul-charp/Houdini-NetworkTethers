import traceback

try:
    import tethers
    tethers.install()
except Exception:
    traceback.print_exc()
