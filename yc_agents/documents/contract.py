from copy import deepcopy


CONTRACT_COLLECTIONS = ("elements", "tables", "complex_objects")
CONTRACT_ACTIONS = {"preserve", "rewrite", "reuse_structure", "confirm", "delete"}


def _legacy_confirm_collection(element_id):
    value = str(element_id or "").casefold()
    if value.startswith("body.tbl") or ".tbl" in value:
        return "tables"
    if any(token in value for token in ("smartart", "chart", "object", "ole", "textbox", "drawing")):
        return "complex_objects"
    return "elements"


def _normalize_legacy_confirm(value):
    """Convert the model's historical ``confirm[].decision`` shape to canonical items."""
    if "confirm" not in value:
        return value
    raw_items = value.pop("confirm")
    if not isinstance(raw_items, list):
        raise ValueError("template contract confirm must be a list")

    canonical_ids = {
        str(item.get("element_id") or item.get("id") or "").strip()
        for collection in CONTRACT_COLLECTIONS
        for item in value.get(collection, [])
        if isinstance(item, dict)
    }
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("Each template contract confirm item must be an object")
        element_id = str(item.get("element_id") or item.get("id") or "").strip()
        if not element_id:
            raise ValueError("Each template contract confirm item requires element_id")
        action = str(item.get("decision") or item.get("action") or "confirm").strip().lower()
        if action not in CONTRACT_ACTIONS:
            allowed = ", ".join(sorted(CONTRACT_ACTIONS))
            raise ValueError(
                f"Unsupported template contract action for {element_id}: {action}. "
                f"Use one of: {allowed}"
            )
        if element_id in canonical_ids:
            continue
        collection = _legacy_confirm_collection(element_id)
        canonical_item = {
            key: deepcopy(item[key])
            for key in item
            if key not in {"id", "decision", "action"}
        }
        canonical_item.update({"element_id": element_id, "action": action})
        value.setdefault(collection, []).append(canonical_item)
        canonical_ids.add(element_id)
    return value


def normalize_template_contract(contract, *, reset_confirmation=False):
    """Return a validated contract and accept legacy ``id`` as an element_id alias."""
    if not isinstance(contract, dict):
        raise ValueError("template contract must be an object")
    value = _normalize_legacy_confirm(deepcopy(contract))

    for collection in CONTRACT_COLLECTIONS:
        raw_items = value.get(collection, [])
        if not isinstance(raw_items, list):
            raise ValueError(f"template contract {collection} must be a list")
        normalized = []
        seen = set()
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError(f"Each template contract {collection} item must be an object")
            explicit_id = str(item.get("element_id") or "").strip()
            legacy_id = str(item.get("id") or "").strip()
            if explicit_id and legacy_id and explicit_id != legacy_id:
                raise ValueError(
                    f"Conflicting element_id and id in template contract {collection}: "
                    f"{explicit_id!r} != {legacy_id!r}"
                )
            element_id = explicit_id or legacy_id
            if not element_id:
                raise ValueError(f"Each template contract {collection} item requires element_id")
            if element_id in seen:
                raise ValueError(f"Duplicate template contract element_id in {collection}: {element_id}")
            seen.add(element_id)
            action = str(item.get("action") or "confirm").strip().lower()
            if action not in CONTRACT_ACTIONS:
                allowed = ", ".join(sorted(CONTRACT_ACTIONS))
                raise ValueError(
                    f"Unsupported template contract action for {element_id}: {action}. "
                    f"Use one of: {allowed}"
                )
            canonical_item = {key: deepcopy(val) for key, val in item.items() if key != "id"}
            canonical_item["element_id"] = element_id
            canonical_item["action"] = action
            normalized.append(canonical_item)
        value[collection] = normalized

    defaults = value.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("template contract defaults must be an object")
    for key, action in defaults.items():
        normalized_action = str(action or "confirm").strip().lower()
        if normalized_action not in CONTRACT_ACTIONS:
            raise ValueError(f"Unsupported default template contract action for {key}: {action}")
        defaults[key] = normalized_action
    value["defaults"] = defaults

    unresolved = value.get("unresolved", [])
    if not isinstance(unresolved, list):
        raise ValueError("template contract unresolved must be a list")
    value["unresolved"] = [str(item) for item in unresolved if str(item).strip()]

    if reset_confirmation:
        value["confirmed"] = False
        value.pop("confirmed_at", None)
    else:
        value["confirmed"] = bool(value.get("confirmed", False))
    return value


def contract_semantics(contract):
    value = normalize_template_contract(contract)
    value.pop("confirmed", None)
    value.pop("confirmed_at", None)
    return value


def merge_template_contract(existing, patch):
    """Merge a partial contract patch by element_id without losing earlier decisions."""
    if not isinstance(patch, dict):
        raise ValueError("template contract patch must be an object")
    current = normalize_template_contract(existing or {})
    incoming = normalize_template_contract(patch)
    merged = deepcopy(current)

    for collection in CONTRACT_COLLECTIONS:
        if collection not in patch and not ("confirm" in patch and incoming.get(collection)):
            continue
        items = {
            item["element_id"]: deepcopy(item)
            for item in current.get(collection, [])
        }
        for item in incoming.get(collection, []):
            items[item["element_id"]] = deepcopy(item)
        merged[collection] = list(items.values())

    if "defaults" in patch:
        defaults = dict(current.get("defaults") or {})
        defaults.update(incoming.get("defaults") or {})
        merged["defaults"] = defaults
    if "unresolved" in patch:
        merged["unresolved"] = list(incoming.get("unresolved") or [])

    reserved = set(CONTRACT_COLLECTIONS) | {
        "confirm",
        "defaults",
        "unresolved",
        "confirmed",
        "confirmed_at",
    }
    for key, value in patch.items():
        if key not in reserved:
            merged[key] = deepcopy(value)
    return normalize_template_contract(merged)
