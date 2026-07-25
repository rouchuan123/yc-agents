from copy import deepcopy


_CHILD_ALIASES = ("children", "sections", "chapters")


def normalize_outline(outline):
    """Return the one canonical, recursive outline representation."""
    if not isinstance(outline, dict):
        raise ValueError("outline must be an object")
    if "sections" in outline and "chapters" in outline:
        raise ValueError("outline must not contain both sections and chapters")
    roots = outline.get("sections", outline.get("chapters"))
    if not isinstance(roots, list) or not roots:
        raise ValueError("outline.sections must be a non-empty list (chapters is accepted as an input alias)")

    seen = set()
    generated_ids = 0

    def visit(items, level, parent_id):
        nonlocal generated_ids
        if level > 9:
            raise ValueError("DOCX heading hierarchy cannot be deeper than 9 levels")
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each outline section must be an object")
            if item.get("id"):
                section_id = str(item["id"]).strip()
            else:
                generated_ids += 1
                section_id = f"section-{generated_ids}"
            if not section_id:
                raise ValueError("Each outline section requires a non-empty id")
            if section_id in seen:
                raise ValueError(f"Duplicate outline section id: {section_id}")
            seen.add(section_id)

            supplied_level = item.get("level")
            if supplied_level is not None:
                try:
                    supplied_level = int(supplied_level)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid outline level for {section_id}: {supplied_level}") from exc
                if supplied_level != level:
                    raise ValueError(
                        f"Outline level does not match nesting for {section_id}: expected {level}, got {supplied_level}"
                    )
            if "parent_id" in item and item.get("parent_id") != parent_id:
                raise ValueError(
                    f"Outline parent_id does not match nesting for {section_id}: expected {parent_id!r}"
                )

            child_keys = [key for key in _CHILD_ALIASES if key in item]
            if len(child_keys) > 1:
                raise ValueError(f"Outline section {section_id} contains multiple child list aliases: {child_keys}")
            children = item.get(child_keys[0], []) if child_keys else []
            if not isinstance(children, list):
                raise ValueError(f"Outline children must be a list for section: {section_id}")

            node = {
                key: deepcopy(value)
                for key, value in item.items()
                if key not in _CHILD_ALIASES and key not in {"level", "parent_id"}
            }
            node.update(
                {
                    "id": section_id,
                    "title": str(item.get("title") or section_id),
                    "purpose": str(item.get("purpose") or ""),
                    "required": bool(item.get("required", True)),
                    "target_role": str(item.get("target_role") or f"heading_{level}"),
                    "level": level,
                    "parent_id": parent_id,
                    "children": visit(children, level + 1, section_id),
                }
            )
            normalized.append(node)
        return normalized

    value = {key: deepcopy(val) for key, val in outline.items() if key not in {"sections", "chapters"}}
    value["sections"] = visit(roots, 1, None)
    return value


def validate_canonical_outline(outline):
    """Reject aliases or hierarchy metadata that does not match the recursive tree."""
    if not isinstance(outline, dict) or "sections" not in outline or "chapters" in outline:
        raise ValueError("Document outline is not canonical; call set_plan/set_outline again before confirm_plan")
    normalized = normalize_outline(outline)
    if normalized != outline:
        raise ValueError("Document outline is not canonical; call set_plan/set_outline again before confirm_plan")
    return normalized


def flatten_outline(outline):
    canonical = validate_canonical_outline(outline)
    flattened = []

    def visit(items):
        for item in items:
            flattened.append({key: deepcopy(value) for key, value in item.items() if key != "children"})
            visit(item["children"])

    visit(canonical["sections"])
    return flattened
