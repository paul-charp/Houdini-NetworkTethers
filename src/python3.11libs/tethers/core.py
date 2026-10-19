"""Leader -> follower positional links between network editor items.

Links are stored as JSON in the parent network's user data, the same way
the network editor stores background images, so they are saved with the hip.

    network.userData("tethers") ->
        {"<kind>:<name>": {"leader": "<kind>:<name>", "offset": [x, y]}}

The key is the follower; each follower has exactly one leader. The offset is
follower.position() - leader.position(), only used to re-place followers
when a node leader is moved by something other than a network editor drag
(layout, align, scripts).
"""

import contextlib
import json

import hou

USER_DATA_KEY = "tethers"

_KINDS = (
    (hou.Node, "node"),
    (hou.StickyNote, "sticky"),
    (hou.NetworkBox, "box"),
    (hou.NetworkDot, "dot"),
)

_suspend_depth = 0


class LinkError(Exception):
    pass


# -- Item keys --------------------------------------------------------------

def item_key(item):
    for cls, kind in _KINDS:
        if isinstance(item, cls):
            return "%s:%s" % (kind, item.name())
    return None


def find_item(network, key):
    kind, _, name = key.partition(":")
    if kind == "node":
        return network.node(name)
    if kind == "sticky":
        return network.findStickyNote(name)
    if kind == "box":
        return network.findNetworkBox(name)
    if kind == "dot":
        for dot in network.networkDots():
            if dot.name() == name:
                return dot
    return None


def is_linkable(item):
    return item_key(item) is not None


# -- Storage ----------------------------------------------------------------

def _load(network):
    raw = network.userData(USER_DATA_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _save(network, table):
    if table:
        network.setUserData(USER_DATA_KEY, json.dumps(table, sort_keys=True))
    elif network.userData(USER_DATA_KEY) is not None:
        network.destroyUserData(USER_DATA_KEY)


def links(network):
    """Return [(follower, leader, offset)] for every link whose items exist.

    Dangling entries are skipped, not removed: this is called on every
    network editor event and must not write to the scene.
    """
    if network is None:
        return []
    result = []
    for follower_key, data in _load(network).items():
        follower = find_item(network, follower_key)
        leader = find_item(network, data.get("leader", ""))
        if follower is not None and leader is not None:
            result.append((follower, leader, hou.Vector2(data.get("offset", (0, 0)))))
    return result


def prune(network):
    """Remove links whose items no longer exist."""
    table = _load(network)
    kept = {
        key: data for key, data in table.items()
        if find_item(network, key) is not None
        and find_item(network, data.get("leader", "")) is not None
    }
    if kept != table:
        _save(network, kept)


# -- Queries ----------------------------------------------------------------

def leader_of(item):
    data = _load(item.parent()).get(item_key(item))
    if not data:
        return None
    return find_item(item.parent(), data["leader"])


def followers_of(item):
    key = item_key(item)
    return [f for f, l, _ in links(item.parent()) if item_key(l) == key]


def followers_closure(items):
    """All followers of `items`, recursively, excluding `items` themselves."""
    items = list(items)
    if not items:
        return []
    by_leader = {}
    for network in {i.parent() for i in items}:
        for follower, leader, _ in links(network):
            by_leader.setdefault(leader, []).append(follower)
    if not by_leader:
        return []

    seen = set(items)
    result = []
    stack = list(items)
    while stack:
        for follower in by_leader.get(stack.pop(), ()):
            if follower not in seen:
                seen.add(follower)
                result.append(follower)
                stack.append(follower)
    return result


def leaders_chain(item):
    """Leaders of `item`, nearest first."""
    chain = []
    leader = leader_of(item)
    while leader is not None and leader not in chain:
        chain.append(leader)
        leader = leader_of(leader)
    return chain


def linked_component(items):
    """`items` plus everything linked to them, up and down the chains."""
    component = set(items)
    roots = set()
    for item in items:
        chain = leaders_chain(item)
        component.update(chain)
        roots.add(chain[-1] if chain else item)
    component.update(followers_closure(roots))
    return component


# -- Edits ------------------------------------------------------------------

def link(followers, leader):
    """Make each item in `followers` follow `leader`. Returns the linked items.

    An item that already follows something is re-linked to `leader`.
    """
    network = leader.parent()
    if not is_linkable(leader):
        raise LinkError("%s can't be a leader." % leader.name())
    prune(network)
    table = _load(network)
    leader_key = item_key(leader)
    blocked = {leader} | set(leaders_chain(leader))
    linked = []
    for follower in followers:
        if follower == leader or not is_linkable(follower):
            continue
        if follower.parent() != network:
            raise LinkError("%s isn't in the same network as %s."
                            % (follower.name(), leader.name()))
        if follower in blocked:
            raise LinkError("Linking %s to %s would make a cycle."
                            % (follower.name(), leader.name()))
        offset = follower.position() - leader.position()
        table[item_key(follower)] = {"leader": leader_key,
                                     "offset": [offset.x(), offset.y()]}
        linked.append(follower)
    with hou.undos.group("Link items"):
        _save(network, table)
    ensure_callbacks(network)
    return linked


def unlink(items):
    """Remove the links of `items`, both as followers and as leaders."""
    by_network = {}
    for item in items:
        by_network.setdefault(item.parent(), set()).add(item_key(item))
    removed = 0
    with hou.undos.group("Unlink items"):
        for network, keys in by_network.items():
            prune(network)
            table = _load(network)
            kept = {k: d for k, d in table.items()
                    if k not in keys and d.get("leader") not in keys}
            removed += len(table) - len(kept)
            _save(network, kept)
    return removed


def update_offsets(items):
    """Store the current offset of every link that touches `items`."""
    by_network = {}
    for item in items:
        if is_linkable(item):
            by_network.setdefault(item.parent(), set()).add(item_key(item))
    for network, keys in by_network.items():
        table = _load(network)
        changed = False
        for follower_key, data in table.items():
            if follower_key not in keys and data.get("leader") not in keys:
                continue
            follower = find_item(network, follower_key)
            leader = find_item(network, data.get("leader", ""))
            if follower is None or leader is None:
                continue
            offset = follower.position() - leader.position()
            value = [offset.x(), offset.y()]
            if value != data.get("offset"):
                data["offset"] = value
                changed = True
        if changed:
            _save(network, table)


def place_followers(leader):
    """Move the followers of `leader`, recursively, to their stored offsets."""
    network = leader.parent()
    by_leader = {}
    for follower, lead, offset in links(network):
        by_leader.setdefault(lead, []).append((follower, offset))
    stack = [leader]
    seen = {leader}
    # Follower moves are derived from the leader: keeping them out of the undo
    # stack means undoing the leader's move re-places them through this same
    # callback instead of fighting it.
    with hou.undos.disabler(), suspended():
        while stack:
            lead = stack.pop()
            for follower, offset in by_leader.get(lead, ()):
                if follower in seen:
                    continue
                seen.add(follower)
                target = lead.position() + offset
                if (follower.position() - target).length() > 1e-6:
                    follower.setPosition(target)
                stack.append(follower)


@contextlib.contextmanager
def suspended():
    """Ignore PositionChanged callbacks, e.g. while a drag applies its moves."""
    global _suspend_depth
    _suspend_depth += 1
    try:
        yield
    finally:
        _suspend_depth -= 1


# -- Node callbacks ---------------------------------------------------------

_NODE_EVENTS = (hou.nodeEventType.PositionChanged, hou.nodeEventType.NameChanged)


def _on_node_event(node, event_type, **kwargs):
    try:
        if event_type == hou.nodeEventType.PositionChanged:
            if not _suspend_depth:
                place_followers(node)
        elif event_type == hou.nodeEventType.NameChanged:
            _rekey_renamed(node)
    except hou.ObjectWasDeleted:
        pass


_on_node_event.tethers = True


def _rekey_renamed(node):
    network = node.parent()
    table = _load(network)
    new_key = item_key(node)
    if new_key in table or any(d.get("leader") == new_key for d in table.values()):
        return
    keys = set(table) | {d.get("leader") for d in table.values()}
    missing = [k for k in keys
               if k.startswith("node:") and find_item(network, k) is None]
    if len(missing) != 1:
        return
    old_key = missing[0]
    renamed = {}
    for key, data in table.items():
        if data.get("leader") == old_key:
            data["leader"] = new_key
        renamed[new_key if key == old_key else key] = data
    _save(network, renamed)


def ensure_callbacks(network):
    """Register the node callback on every node taking part in a link."""
    nodes = set()
    for follower, leader, _ in links(network):
        nodes.update(i for i in (follower, leader) if isinstance(i, hou.Node))
    for node in nodes:
        for event_types, callback in node.eventCallbacks():
            if getattr(callback, "tethers", False):
                node.removeEventCallback(event_types, callback)
        node.addEventCallback(_NODE_EVENTS, _on_node_event)


def linked_networks():
    root = hou.node("/")
    networks = [n for n in (root,) + root.allSubChildren(recurse_in_locked_nodes=False)
                if n.userData(USER_DATA_KEY)]
    return networks


def _on_hip_event(event_type):
    if event_type in (hou.hipFileEventType.AfterLoad, hou.hipFileEventType.AfterMerge):
        for network in linked_networks():
            ensure_callbacks(network)


_on_hip_event.tethers = True


def install_hip_callbacks():
    for callback in hou.hipFile.eventCallbacks():
        if getattr(callback, "tethers", False) and callback.__module__ == __name__:
            hou.hipFile.removeEventCallback(callback)
    hou.hipFile.addEventCallback(_on_hip_event)
    for network in linked_networks():
        ensure_callbacks(network)
