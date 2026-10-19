# Houdini-NetworkTethers: make sure the network editor toolbar file with the
# tether buttons exists for this Houdini build. pythonrc runs before the UI is
# built, so a file generated here is used in this same session.
import os
import traceback


def _ensure_tethers_toolbar():
    import hou
    from tethers import toolbar

    build = hou.applicationVersionString()
    try:
        if toolbar.ensure(os.environ["HFS"], build):
            print("Houdini-NetworkTethers: toolbar generated for Houdini %s." % build)
    except toolbar.ToolbarError as e:
        print("Houdini-NetworkTethers: %s" % e)


try:
    _ensure_tethers_toolbar()
except Exception:
    traceback.print_exc()
