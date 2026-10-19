"""Network editor event context: click the leader for the pending followers.

Pushed by tethers.tools.pick_leader() with
editor.pushEventContext("tetherspick", {"followers": [...]}).
Draws a rubber band from the followers to the cursor, highlights the item
under it, links on click. Escape or a click on empty space cancels.
"""

import traceback

import hou
import nodegraphbase as base
import nodegraphdisplay as display
import nodegraphview as view
from canvaseventtypes import KeyboardEvent, MouseEvent

from tethers import core
from tethers import editor as nl_editor


def handleEvent(uievent, last_handler_coroutine):
    handler_coroutine = last_handler_coroutine
    if handler_coroutine is None:
        handler_coroutine = _handle_event_coroutine()
        next(handler_coroutine)
    if not handler_coroutine.gi_running:
        try:
            handler_coroutine.send(uievent)
        except StopIteration:
            handler_coroutine = None
    return handler_coroutine


def _target_under(uievent, followers):
    component = uievent.selected if uievent.eventtype == "mousedown" else uievent.located
    item = component.item if component is not None else None
    if item is None or not core.is_linkable(item) or item in followers:
        return None
    return item


def _shapes(editor, followers, mouse_pos, target):
    color = nl_editor.LINK_COLOR
    shapes = []
    end_rect = editor.itemRect(target) if target is not None else None
    # Arrows run leader -> follower, as they will once linked.
    for follower in followers:
        rect = editor.itemRect(follower)
        start = (nl_editor._edge_point(end_rect, rect.center())
                 if end_rect is not None else mouse_pos)
        end = nl_editor._edge_point(rect, start)
        # Dashed while free, solid once it snaps to a candidate leader.
        shapes.extend(nl_editor.arrow_shapes(
            editor, start, end, color, 0.85, dashed=end_rect is None))
    return shapes


def _handle_event_coroutine():
    editor = None
    handler = None
    pressed_target = None
    exit_exception = None

    while True:
        uievent = yield
        if editor is None:
            editor = uievent.editor
            editor.setPrompt("Click the leader. Esc cancels.")
        data = editor.eventContextData()
        followers = data["followers"]

        try:
            # Let view panning/zooming run to completion.
            if handler is not None:
                handler = handler.handleEvent(uievent, [])
                if not isinstance(handler, base.EventHandler):
                    handler = None
                continue

            if isinstance(uievent, KeyboardEvent):
                if uievent.eventtype.endswith("keyhit") and \
                   display.setKeyPrompt(editor, uievent, "h.pane.wsheet.cancel"):
                    break
                continue

            if not isinstance(uievent, MouseEvent):
                continue

            if uievent.eventtype == "mousewheel":
                view.scaleWithMouseWheel(uievent)

            elif uievent.eventtype == "mousedown":
                if base.isPanEvent(uievent):
                    handler = base.ViewPanHandler(uievent)
                elif base.isScaleEvent(uievent):
                    handler = base.ViewScaleHandler(uievent)
                if handler is not None:
                    handler = handler.handleEvent(uievent, [])
                    if not isinstance(handler, base.EventHandler):
                        handler = None
                    continue
                pressed_target = _target_under(uievent, followers)

            elif uievent.eventtype == "mouseup":
                if pressed_target is not None:
                    try:
                        data["linked"] = core.link(followers, pressed_target)
                        data["leader"] = pressed_target
                    except core.LinkError as e:
                        editor.flashMessage("STATUS_error", str(e), 3.0)
                break

            mouse_pos = editor.posFromScreen(uievent.mousepos)
            target = pressed_target or _target_under(uievent, followers)
            editor.setOverlayShapes(_shapes(editor, followers, mouse_pos, target))

        except Exception as ex:
            exit_exception = ex
            break

    if editor is not None:
        editor.setOverlayShapes([])
        editor.setPrompt("")
        editor.popEventContext()
    if exit_exception is not None:
        traceback.print_exception(exit_exception)
