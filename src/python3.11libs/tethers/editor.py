"""Network editor integration: followers move live with drags, links are drawn.

Wrappers around the stock nodegraph code:

- MovableItemMoveHandler.getItemsToMove builds the list of items a drag
  moves. Appending followers there makes them preview, snap, drop and undo
  exactly like the items the user grabbed.
- EditorUpdates.applyToEditor runs after every network editor event and
  replaces the editor's shapes. Adding the link shapes there keeps them on
  screen and in sync with drag previews.
- createEventHandler handles the Cycle Tether Display hotkey.
"""

import traceback

import hou
import nodegraph
import nodegraphdisplay
import nodegraphutils
from canvaseventtypes import KeyboardEvent

from tethers import core

DISPLAY_PREF = "tethers_display"
DISPLAY_MODES = ("selected", "all", "off")
DEFAULT_MODE = "selected"

LINK_COLOR = hou.Color(1.0, 0.62, 0.15)

_originals = {}
_registered_editors = set()
# The move handler of the drag in progress, so link shapes can follow the
# drag preview (hou.NetworkAnimValue exposes no getters).
_drag = {"handler": None}


# -- Drag -------------------------------------------------------------------

def _get_items_to_move(self, uievent):
    _drag["handler"] = self
    items = _originals["getItemsToMove"](self, uievent)
    # Alt-drag duplicates the dragged items; leave followers out of the copy.
    if uievent.modifierstate.alt:
        return items
    try:
        present = set(items)
        extra = []
        for follower in core.followers_closure(items):
            for item in [follower] + (list(follower.items())
                                      if isinstance(follower, hou.NetworkBox) else []):
                if item not in present:
                    present.add(item)
                    extra.append(item)
        if extra:
            items.extend(extra)
            uievent.editor.setDragSourceData(items)
    except Exception:
        traceback.print_exc()
    return items


def _apply_adjustments(self, uievent):
    if self.isPerformingCopy(uievent):
        return _originals["applyAdjustments"](self, uievent)
    with hou.undos.group("Move items", uievent.editor), core.suspended():
        _originals["applyAdjustments"](self, uievent)
        try:
            core.update_offsets(self.moveitems)
        except Exception:
            traceback.print_exc()


# -- Display ----------------------------------------------------------------

def display_mode(editor):
    if editor.name() not in _registered_editors:
        editor.registerPref(DISPLAY_PREF, DEFAULT_MODE, True)
        _registered_editors.add(editor.name())
    mode = editor.getPref(DISPLAY_PREF)
    return mode if mode in DISPLAY_MODES else DEFAULT_MODE


# The menus' radio strips reflect this hscript global variable (they don't see
# environment variables). It is unset around hip saves so it never lands in a
# scene file.
MENU_VARIABLE = "TETHERS_DISPLAY"


def _network_editors():
    return [p for p in hou.ui.paneTabs() if isinstance(p, hou.NetworkEditor)]


def current_mode():
    editors = _network_editors()
    return display_mode(editors[0]) if editors else DEFAULT_MODE


def sync_menu(mode=None):
    hou.hscript("set -g %s = %s" % (MENU_VARIABLE, mode or current_mode()))
    hou.hscript("varchange %s" % MENU_VARIABLE)


def _on_hip_event(event_type):
    if event_type == hou.hipFileEventType.BeforeSave:
        hou.hscript("set -u %s" % MENU_VARIABLE)
    elif event_type in (hou.hipFileEventType.AfterSave,
                        hou.hipFileEventType.AfterLoad,
                        hou.hipFileEventType.AfterClear):
        sync_menu()


_on_hip_event.tethers = True


def set_display(mode, editor=None):
    """Set the link display mode for every network editor."""
    if mode not in DISPLAY_MODES:
        return
    for pane in _network_editors():
        display_mode(pane)  # registers the pref
        pane.setPref(DISPLAY_PREF, mode)
        refresh(pane)
    sync_menu(mode)
    if editor is not None:
        labels = {"selected": "Tethers: selected", "all": "Tethers: all", "off": "Tethers: hidden"}
        editor.flashMessage(None, labels[mode], 1.5)


def cycle_display(editor):
    mode = display_mode(editor)
    mode = DISPLAY_MODES[(DISPLAY_MODES.index(mode) + 1) % len(DISPLAY_MODES)]
    set_display(mode, editor)
    return mode


def refresh(editor):
    """Redraw link shapes now, without waiting for the next editor event."""
    mode = display_mode(editor)
    editor.setShapes(link_shapes(editor, mode) if mode != "off" else [])


def _edge_point(rect, toward):
    """Point where the segment from rect's center to `toward` leaves rect."""
    center = rect.center()
    d = toward - center
    half = (rect.max() - rect.min()) * 0.5
    scales = [half[i] / abs(d[i]) for i in (0, 1) if abs(d[i]) > 1e-9]
    if not scales:
        return center
    return center + d * min(1.0, min(scales))


def arrow_shapes(editor, start, end, color=LINK_COLOR, alpha=1.0, dashed=False):
    """Antialiased arrow from `start` (round anchor) to `end` (filled head).

    Sizes are in screen pixels, converted to network units at the current
    zoom, so the arrow reads the same at every zoom level.
    """
    px = editor.lengthFromScreen(1.0)
    d = end - start
    length = d.length()
    if length < 1e-6:
        return []
    u = d * (1.0 / length)
    n = hou.Vector2(-u[1], u[0])

    anchor_r = 4.0 * px
    gap = 2.0 * px
    head_len = min(14.0 * px, max(0.0, length - 2 * anchor_r - 2 * gap) * 0.6)
    head_half = head_len * 0.5
    tip = end - u * gap
    base = tip - u * head_len
    # Shapes draw under items: keep the anchor just outside the leader.
    anchor = start + u * (anchor_r + gap)

    shapes = [hou.NetworkShapeNodeShape(
        hou.BoundingRect(anchor - hou.Vector2(anchor_r, anchor_r),
                         anchor + hou.Vector2(anchor_r, anchor_r)),
        "circle", color, alpha, True, False)]
    shaft_start = anchor + u * anchor_r
    if (base - shaft_start).dot(u) > 0:
        shapes.append(hou.NetworkShapeLine(
            shaft_start, base + u * px, color, alpha * 0.9, 2.0, False, True, dashed))
    if head_len > 0:
        # No polygon shape exists: fill the head with a fan of smooth lines.
        steps = 10
        for i in range(steps + 1):
            t = -1.0 + 2.0 * i / steps
            shapes.append(hou.NetworkShapeLine(
                tip, base + n * (head_half * t), color, alpha, 1.5, False, True, False))
    return shapes


def link_shapes(editor, mode, moving=(), delta=None):
    """Shapes for the links of the current network.

    Items in `moving` are drawn shifted by `delta` (a drag preview).
    """
    network = editor.pwd()
    pairs = core.links(network)
    if not pairs:
        return []
    if mode == "selected":
        selected = network.selectedItems()
        if not selected:
            return []
        component = core.linked_component(selected)
        pairs = [p for p in pairs if p[0] in component]

    def rect_of(item):
        rect = editor.itemRect(item, False)
        # A box's stored size can be smaller than what the editor draws
        # around its contents.
        if isinstance(item, hou.NetworkBox) and not item.isMinimized():
            for child in item.items():
                rect.enlargeToContain(editor.itemRect(child, False))
        if delta is not None and item in moving:
            rect.translate(delta)
        return rect

    shapes = []
    for follower, leader, _ in pairs:
        leader_rect = rect_of(leader)
        follower_rect = rect_of(follower)
        start = _edge_point(leader_rect, follower_rect.center())
        end = _edge_point(follower_rect, leader_rect.center())
        shapes.extend(arrow_shapes(editor, start, end))
    return shapes


def _apply_to_editor(self, editor):
    try:
        mode = display_mode(editor)
        if mode != "off":
            moving, delta = (), None
            handler = _drag["handler"]
            # Adjustments are only present while a drag preview is showing.
            if handler is not None and handler.item in self.adj_items:
                moving = set(handler.moveitems)
                delta = handler.drag
            self.shapes = list(self.shapes) + link_shapes(editor, mode, moving, delta)
    except hou.ObjectWasDeleted:
        pass
    except Exception:
        traceback.print_exc()
    _originals["applyToEditor"](self, editor)


# -- Hotkey -------------------------------------------------------------------

# Listed in the Hotkey Manager under the network editor, with no key assigned.
# Like nodegraph's own hotkeys, the key is matched in Python, so it needs no
# menu item.
CYCLE_DISPLAY_SYMBOL = "h.pane.wsheet.tethers_cycle_display"


def register_hotkeys():
    hou.hotkeys.addCommand(CYCLE_DISPLAY_SYMBOL, "Cycle Tether Display",
                           "Cycle the tether display: hide, selected items, all items")
    # Without the binding hou.ui.isKeyMatch rejects the symbol as invalid.
    hou.hotkeys.addCommandBinding("h.pane.wsheet", CYCLE_DISPLAY_SYMBOL)


def _create_event_handler(uievent, pending_actions):
    if isinstance(uievent, KeyboardEvent) and uievent.eventtype.endswith("keyhit") \
       and nodegraphdisplay.setKeyPrompt(uievent.editor, uievent, CYCLE_DISPLAY_SYMBOL):
        cycle_display(uievent.editor)
        return None, True
    return _originals["createEventHandler"](uievent, pending_actions)


# -- Install ----------------------------------------------------------------

_PATCHES = (
    (nodegraph.MovableItemMoveHandler, "getItemsToMove", _get_items_to_move),
    (nodegraph.MovableItemMoveHandler, "applyAdjustments", _apply_adjustments),
    (nodegraphutils.EditorUpdates, "applyToEditor", _apply_to_editor),
    (nodegraph, "createEventHandler", _create_event_handler),
)


def install():
    for cls, name, wrapper in _PATCHES:
        current = getattr(cls, name)
        if getattr(current, "tethers", False):
            # Reinstall after a reload: keep the stock function.
            _originals[name] = current.tethers_original
        else:
            _originals[name] = current
        wrapper.tethers = True
        wrapper.tethers_original = _originals[name]
        setattr(cls, name, wrapper)
    for callback in hou.hipFile.eventCallbacks():
        if getattr(callback, "tethers", False) and callback.__module__ == __name__:
            hou.hipFile.removeEventCallback(callback)
    hou.hipFile.addEventCallback(_on_hip_event)
    sync_menu()
    register_hotkeys()


def uninstall():
    for cls, name, wrapper in _PATCHES:
        current = getattr(cls, name)
        if getattr(current, "tethers", False):
            setattr(cls, name, current.tethers_original)


def is_installed():
    return all(getattr(getattr(cls, name), "tethers", False)
               for cls, name, _ in _PATCHES)
