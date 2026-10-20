# Houdini-NetworkTethers

Tether network editor items to each other by position in Houdini 21: sticky
notes, network boxes, dots and nodes follow a leader when it moves, the way a
background image can be pinned to a node.

- Drag a leader and its followers move with it, live, in one undo step.
  Chains work; cycles are refused.
- Tethers are drawn as orange arrows (leader → follower). Tethers menu:
  hide, show for selected items, show for all. A **Cycle Tether Display**
  hotkey (network editor context, no key assigned) loops through them.
- Toolbar buttons, a **Tethers** menu and node right-click entries:
  Tether to Leader (then click the leader), Untether, Select Tethered.
- Tethers are stored in the parent network's user data and save with the hip.

## Install

1. Download `Houdini-NetworkTethers-<version>.zip` from the releases and
   extract it to a writable folder.
2. Copy `tethers.json` into `$HOUDINI_USER_PREF_DIR/packages/` (for example
   `Documents/houdini21.0/packages`) and set `TETHERS_ROOT` to the extracted
   folder.
3. Start Houdini.

The toolbar buttons need a file derived from your own Houdini install. At
startup the package generates it once per Houdini build, into
`generated/<build>/`, and each build loads its own. One install serves
several Houdini 21 builds; the extracted folder must be writable.

## Hotkeys

No keys are assigned by default. To add your own:

1. Choose **Edit › Hotkeys** in Houdini's main menu.
2. In the context tree, select **Panes › Network Editor**.
3. Type `tether` in the filter box.
4. Select an action, click its key field and press the key you want.

| Action | Hotkey symbol |
| --- | --- |
| Tether to Leader... | `h.pane.wsheet.tethers_tether` |
| Untether | `h.pane.wsheet.tethers_untether` |
| Select Tethered | `h.pane.wsheet.tethers_select_tethered` |
| Cycle Tether Display | `h.pane.wsheet.tethers_cycle_display` |
| Hide | `h.pane.wsheet.tethers_display_off` |
| Show for Selected Items | `h.pane.wsheet.tethers_display_selected` |
| Show for All Items | `h.pane.wsheet.tethers_display_all` |

The keys work while the cursor is over a network editor. Cycle Tether
Display loops Show for Selected Items → Show for All Items → Hide.

## Development

Point the prefs package at `src/`
(`"TETHERS_ROOT": ".../Houdini-NetworkTethers/src"`) and restart Houdini after
menu or toolbar changes.

```
python build.py build [--hfs PATH]   # build/: package + toolbar for a local Houdini
python build.py dist                 # dist/: release zip, no SideFX content
python build.py release [--draft]    # dist + tag v<version> + GitHub release
```

The version lives in `src/python3.11libs/tethers/__init__.py`; release notes
come from its section in `CHANGELOG.md`.

## Layout

| Path | Role |
| --- | --- |
| `src/python3.11libs/tethers/` | storage and chains (`core`), editor hooks and drawing (`editor`), menu entry points (`tools`), toolbar generator (`toolbar`) |
| `src/python3.11libs/tetherspick.py` | click-the-leader network editor mode |
| `src/python3.11libs/pythonrc.py` | generates the toolbar file before the UI loads |
| `src/python3.11libs/uiready.py` | installs the editor hooks |
| `src/NetworkViewMenu.xml` | Tethers menu |
| `src/OPmenu.xml` | node right-click entries |

## How the toolbar buttons work

The network editor toolbar is defined by SideFX's
`config/Applications/FUSE_NetEditorApp.ui`. Houdini ships its text source in
`$HFS/houdini/config/OldUIFiles.cpio.gz`. `tethers.toolbar` extracts it,
inserts three `ACTION_ICONBUTTON`s that send the Tethers menu's actions, and
writes it to `generated/<build>/`, which `tethers.json` puts on
`HOUDINI_PATH` (as `generated/$HOUDINI_VERSION`) ahead of `$HFS`. Nothing
derived from SideFX files is committed or distributed. The buttons only work
while the Tethers menu defines those actions.

The editor hooks wrap functions of SideFX's `nodegraph` Python; re-check them
on each major Houdini version.
