"""Entry points for shelf tools, hotkeys and the node right-click menu."""

import hou

from tethers import core
from tethers import editor as nl_editor


def _editor(kwargs=None):
    pane = (kwargs or {}).get("pane")
    if isinstance(pane, hou.NetworkEditor):
        return pane
    pane = hou.ui.paneTabUnderCursor()
    if isinstance(pane, hou.NetworkEditor):
        return pane
    return hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)


def _selection(editor):
    return [i for i in editor.pwd().selectedItems() if core.is_linkable(i)]


def link_selected(kwargs=None):
    """Selected items follow the leader the user clicks next."""
    editor = _editor(kwargs)
    if editor is None:
        return
    followers = _selection(editor)
    if not followers:
        editor.flashMessage("STATUS_error", "Select the items that should follow first.", 2.5)
        return
    data = {"followers": followers}
    editor.pushEventContext("tetherspick", data)
    leader = data.get("leader")
    if leader is not None:
        count = len(data.get("linked", ()))
        editor.flashMessage(None, "%d item%s tethered to %s"
                            % (count, "" if count == 1 else "s", leader.name()), 2.0)
        nl_editor.refresh(editor)


def unlink_selected(kwargs=None):
    editor = _editor(kwargs)
    if editor is None:
        return
    removed = core.unlink(_selection(editor))
    editor.flashMessage(None, "%d tether%s removed" % (removed, "" if removed == 1 else "s"), 2.0)
    nl_editor.refresh(editor)


def select_linked(kwargs=None):
    editor = _editor(kwargs)
    if editor is None:
        return
    for item in core.linked_component(_selection(editor)):
        item.setSelected(True)
    nl_editor.refresh(editor)


def set_display(mode):
    """Called by the Tethers menu's display radio strip."""
    nl_editor.set_display(mode)


def toggle_display(kwargs=None):
    editor = _editor(kwargs)
    if editor is not None:
        nl_editor.cycle_display(editor)


def _select_menu_node(kwargs):
    node = kwargs["node"]
    if not node.isSelected():
        node.setSelected(True, clear_all_selected=True)
    return {"pane": _editor()}


def link_from_menu(kwargs):
    link_selected(_select_menu_node(kwargs))


def unlink_from_menu(kwargs):
    unlink_selected(_select_menu_node(kwargs))
