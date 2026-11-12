def build_tree(spans: list[dict]) -> list[dict]:
    span_id_lookup = {}

    for span in spans:
        # copy the span (don't change the caller's data) and give it an empty children list
        span_id_lookup[span["id"]] = {**span, "children": [], "orphaned": False}

    span_roots = []

    
    for span in sorted(spans, key=lambda s: s["start_time"]):
        node = span_id_lookup[span["id"]]
        parent_id = span.get("parent_span_id")
        parent = span_id_lookup.get(parent_id) if parent_id else None

        if parent is None or parent is node:
            node["orphaned"] = parent_id is not None   # had a parent id, but that span doesn't exist
            span_roots.append(node)
        else:
            parent["children"].append(node)
    return span_roots
