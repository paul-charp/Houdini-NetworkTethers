"""Generate the network editor toolbar file with the tether buttons.

The network editor's toolbar is defined by SideFX's
config/Applications/FUSE_NetEditorApp.ui. Houdini ships it compiled, but each
build also ships its text source in config/OldUIFiles.cpio.gz (a zip holding
an "odc" cpio archive). This module extracts that source from the local
install, inserts the tether buttons and writes the result into the package's
generated/<build>/ folder. tethers.json puts generated/$HOUDINI_VERSION on
HOUDINI_PATH ahead of $HFS, so each Houdini build loads its own file and
several builds can share one package.

Generated files are derived from SideFX files: never committed or distributed.

No hou import: build.py uses this module outside Houdini.
"""

import io
import os
import zipfile

UI_NAME = "FUSE_NetEditorApp.ui"
ARCHIVE = os.path.join("houdini", "config", "OldUIFiles.cpio.gz")
MEMBER = "Applications/" + UI_NAME
HEADER = "# Houdini-NetworkTethers toolbar for Houdini %s (generated, do not edit)\n"

# The buttons go first in the toolbar's icon group, before the tool palette.
ANCHOR = '\t    { HSTRETCH }\n\n\t    TOGGLE_ICONBUTTON "BUTTONS_node_palette"'

# Each button sends an action defined by the Tethers menu (NetworkViewMenu.xml).
BUTTONS = (
    ("BUTTONS_link", "h.pane.wsheet.tethers_tether", "Tether selected items to a leader"),
    ("BUTTONS_disconnect", "h.pane.wsheet.tethers_untether", "Untether selected items"),
    ("BUTTONS_selectable_on", "h.pane.wsheet.tethers_select_tethered", "Select tethered items"),
)


class ToolbarError(Exception):
    pass


def package_root():
    """The package folder (the one holding python3.11libs)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generated_dir(build, root=None):
    """Where the toolbar file for `build` lives (matches tethers.json's hpath)."""
    return os.path.join(root or package_root(), "generated", build)


def output_path(out_dir):
    return os.path.join(out_dir, "config", "Applications", UI_NAME)


def read_source(hfs):
    """Return SideFX's text source of the toolbar file for the build at `hfs`."""
    archive = os.path.join(hfs, ARCHIVE)
    try:
        with zipfile.ZipFile(archive) as zf:
            data = zf.read(zf.namelist()[0])
    except (OSError, zipfile.BadZipFile, IndexError) as e:
        raise ToolbarError("Can't read %s: %s" % (archive, e))
    stream = io.BytesIO(data)
    while True:
        header = stream.read(76)
        if len(header) < 76 or header[:6] != b"070707":
            break
        name_size = int(header[59:65], 8)
        file_size = int(header[65:76], 8)
        name = stream.read(name_size)[:-1].decode("latin1")
        if name == "TRAILER!!!":
            break
        body = stream.read(file_size)
        if name == MEMBER:
            return body.decode("latin1")
    raise ToolbarError("%s not found in %s" % (MEMBER, archive))


def _button(icon, symbol, help_text):
    return ('\t    ACTION_ICONBUTTON "%s"\n'
            '\t\tSENDSKEY("%s")\n'
            '\t\tVALUE(editorKeyValue)\n'
            '\t\tHELP("%s")\n'
            '\t\tUI_FLAT_ICON_BTN_SIZE_SMALL LOOKFLAT;\n\n') % (icon, symbol, help_text)


def patch(source, build):
    """Insert the tether buttons into SideFX's toolbar source."""
    if source.count(ANCHOR) != 1:
        raise ToolbarError("The toolbar layout of Houdini %s isn't the one this "
                           "version knows; buttons not added." % build)
    added = ("\t    # Houdini-NetworkTethers buttons.\n"
             + "".join(_button(*b) for b in BUTTONS)
             + "\t    { PREF_WIDTH(0.2) }\n\n")
    new_anchor = ANCHOR.replace('\t    TOGGLE_ICONBUTTON', added + '\t    TOGGLE_ICONBUTTON')
    return HEADER % build + source.replace(ANCHOR, new_anchor)


def generated_build(out_dir):
    """The Houdini build the existing generated file was made for, or None."""
    try:
        with open(output_path(out_dir), encoding="latin1") as f:
            first = f.readline()
    except OSError:
        return None
    prefix, _, rest = HEADER.partition("%s")
    if first.startswith(prefix):
        return first[len(prefix):].split(" ", 1)[0]
    return None


def generate(hfs, out_dir, build):
    """Write the patched toolbar file for the build at `hfs`. Returns its path."""
    text = patch(read_source(hfs), build)
    path = output_path(out_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Write then rename, so two Houdini sessions starting together never load
    # a half-written file.
    temp = "%s.%d.tmp" % (path, os.getpid())
    with open(temp, "w", encoding="latin1", newline="\n") as f:
        f.write(text)
    os.replace(temp, path)
    return path


def ensure(hfs, build, root=None):
    """Generate the toolbar file for `build` unless it exists. True if written.

    Files of other builds are left alone.
    """
    out_dir = generated_dir(build, root)
    if generated_build(out_dir) == build:
        return False
    generate(hfs, out_dir, build)
    return True
