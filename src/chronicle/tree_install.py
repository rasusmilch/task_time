"""Incremental iterative Treeview installation; no authoritative state."""
from .project_ui import installation_order


def install(tree, rows, children, *, open_roots=False):
    order = list(installation_order(children))
    selected, scroll = tree.selection(), tree.yview()
    # Surviving children move out before an obsolete former ancestor is erased.
    for key in order:
        row = rows[key]; parent = row['parent']
        fields = {name:row[name] for name in ('text','values','tags') if name in row}
        if not tree.exists(key):
            tree.insert(parent,'end',iid=key,**fields,open=bool(open_roots and not parent))
        else:
            if tree.parent(key)!=parent:tree.move(key,parent,'end')
            old = tree.item(key)
            updates = {k:v for k,v in fields.items() if (tuple(map(str,old[k])) if k=='values' else tuple(old[k]) if k=='tags' else old[k]) != (tuple(map(str,v)) if k=='values' else v)}
            if updates:tree.item(key,**updates)
    existing=[];stack=list(tree.get_children(''))
    while stack:
        key=stack.pop();existing.append(key);stack.extend(tree.get_children(key))
    for key in reversed(existing):
        if key not in rows:tree.delete(key)
    for parent, siblings in children.items():
        if tuple(tree.get_children(parent))!=tuple(siblings):
            for index,key in enumerate(siblings):
                if tree.index(key)!=index:tree.move(key,parent,index)
    surviving=tuple(key for key in selected if key in rows)
    if tree.selection()!=surviving:tree.selection_set(surviving)
    if scroll and tree.yview()!=scroll:tree.yview_moveto(scroll[0])
