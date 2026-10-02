#!/usr/bin/env python3
"""Require every public result statement to have an explicit evidence disposition."""

import argparse
import json
import pathlib
import re
import sys
from html.parser import HTMLParser


STATUSES = {"VERIFIED", "UNKNOWN DISCLOSED", "NONCLAIM", "CUT"}
UNKNOWN_STATES = {"is unknown", "is unavailable", "was not run", "was not measured", "could not be measured"}
UNKNOWN_METRICS = {
    "balance", "billing telemetry", "comparison", "cost", "duration", "latency",
    "measurement", "quota", "result", "score", "status", "usage",
}
ENTITY_RE = re.compile(r"^[A-Z][A-Za-z0-9_.+-]{0,39}$")
CLAUSE_SPLIT_RE = re.compile(
    r"(?:[.!?]+\s+|;\s*|\s+(?i:although|and|as well as|because|but|however|plus|so|therefore|though|while|whereas|yet)\s+|"
    r"(?:,|:)\s+(?=[A-Z][A-Za-z0-9_.+-]*(?:\s|$)))",
)
GENERIC_EVIDENCE_WORDS = {
    "claim", "claims", "content", "data", "evidence", "fact", "facts", "id",
    "measurement", "measurements", "public", "result", "results", "room", "summary", "trace",
    "value", "values",
}
MEASUREMENT_KEYS = {"entity", "predicate", "measure", "value", "source"}
MEASUREMENT_SOURCE_KEYS = {"path", "pointer"}
APPROVED_RAW_EVIDENCE = {
    "room.json", "evidence/claim-evidence.json", "evidence/floor.json", "evidence/usage-sessions.json",
}
RAW_SOURCE_QUALIFIERS = {
    "attribute", "attributes", "metadata", "raw",
}
RAW_COLLECTION_QUALIFIERS = {
    "claim", "claims", "event", "events", "item", "items", "message", "messages", "record",
    "records", "session", "sessions",
}
RAW_LEAF_QUALIFIERS = {"value"}
NONCLAIM_REASONS = {
    "accessible label", "brand", "column header", "command", "control", "document title",
    "heading", "link",
}
CLAIM_LIKE_RE = re.compile(
    r"\b(?:accepted|are|built|builds|can|completed|computed|contains|created|did|does|generated|"
    r"had|handled|has|have|includes|is|made|measured|passed|posted|powers|provides|ran|reads|"
    r"reached|rejected|returns|runs|supports|used|uses|verified|was|were|will|writes|wrote)\b",
    re.IGNORECASE,
)
CLAIM_QUALIFIER_RE = re.compile(
    r"\b(?:accurate|active|available|autonomous|best|better|complete|connected|deployed|disabled|"
    r"disconnected|enabled|end-to-end|faster|fastest|fewer|fully|healthy|higher|highest|independent|"
    r"least|live|lower|lowest|more|most|offline|online|operational|production-ready|public|ready|"
    r"real-time|reliable|running|secure|stopped|successful|unavailable|unhealthy|working|zero-touch)\b",
    re.IGNORECASE,
)
QUANTIFIER_RE = re.compile(
    r"(?:\d|\b(?:all|every|never|no|nobody|none|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|zero)\b)",
    re.IGNORECASE,
)
COMMAND_RE = re.compile(
    r"(?:"
    r"\./\S+(?:\s+.*)?|(?:bash|sh)\s+\S+\.sh(?:\s+.*)?|"
    r"docker\s+(?:build|compose|inspect|pull|push|run|tag)\b(?:\s+.*)?|"
    r"ffmpeg\s+-.+|ffprobe\s+-.+|gh\s+(?:api|pr|repo|run)\b(?:\s+.*)?|"
    r"git\s+(?:archive|diff|log|show|status)\b(?:\s+.*)?|make(?:\s+.*)?|"
    r"(?:npm|pnpm)\s+(?:exec|run|test)\b(?:\s+.*)?|pip3?\s+(?:check|install|list)\b(?:\s+.*)?|"
    r"(?:py\.test|pytest)(?:\s+.*)?|"
    r"python3?\s+(?:-m\s+[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|\S+\.py)(?:\s+.*)?"
    r")",
    re.IGNORECASE,
)
COMMAND_PREFIXES = [
    re.compile(pattern, re.IGNORECASE) for pattern in (
        r"^\./\S+", r"^(?:bash|sh)\s+\S+\.sh",
        r"^docker\s+(?:build|compose|inspect|pull|push|run|tag)\b",
        r"^ffmpeg\b", r"^ffprobe\b", r"^gh\s+(?:api|pr|repo|run)\b",
        r"^git\s+(?:archive|diff|log|show|status)\b", r"^make\b",
        r"^(?:npm|pnpm)\s+(?:exec|run|test)\b", r"^pip3?\s+(?:check|install|list)\b",
        r"^(?:py\.test|pytest)\b",
        r"^python3?\s+(?:-m\s+[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|\S+\.py)",
    )
]
LOCATOR_QUALIFIERS = {"value"}
POLARITY_WORDS = {"failed", "false", "never", "no", "not", "unavailable", "unknown", "without"}
NEUTRAL_HEADING_WORDS = {
    "about", "application", "architecture", "artifact", "command", "content", "data", "deck",
    "demo", "deployment", "detail", "evidence", "factory", "floor", "guide", "holdout", "how",
    "judge", "limitation", "method", "overview", "package", "project", "readme", "reproduction",
    "result", "run", "stage", "summary", "usage", "verification",
}
NONCLAIM_KINDS = {
    "accessible label": {"accessible label"},
    "brand": {"brand"},
    "column header": {"column header"},
    "command": {"code"},
    "control": {"control"},
    "document title": {"document title"},
    "heading": {"heading"},
    "link": {"link"},
}
LOW_INFORMATION_WORDS = {
    "a", "an", "are", "at", "be", "by", "for", "from", "in", "is", "its", "model", "of", "on",
    "our", "per", "result", "run", "stage", "test", "that", "the", "this", "to", "was", "were",
    "with",
}
SEMANTIC_TAGS = {
    "a", "button", "caption", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6",
    "label", "li", "p", "text", "title",
}
CONTEXT_CLASSES = {"clock", "stage-mark", "stat", "who"}
HIDDEN_TAGS = {"script", "style"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def normalize(value):
    return " ".join(str(value).split())


def stem(value):
    value = value.lower()
    if len(value) > 4 and value.endswith("ies"):
        return value[:-3] + "y"
    if len(value) > 3 and value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def words(value):
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    return {stem(word) for word in re.findall(r"[A-Za-z]+|[0-9]+", expanded)}


def claim_clauses(value):
    text = normalize(value)
    clauses = []
    for part in CLAUSE_SPLIT_RE.split(text):
        part = normalize(part).strip(" .,!?:")
        if part:
            clauses.append(part)
    return clauses


def evidence_words(path, pointer, actual, public_text):
    tokens = words(pointer)
    if path == "room.json" or not (isinstance(actual, str) and normalize(actual) == public_text):
        tokens.update(words(actual))
    return {token for token in tokens - GENERIC_EVIDENCE_WORDS if any(char.isalpha() for char in token)}


def command_payload(value):
    for prefix in COMMAND_PREFIXES:
        match = prefix.search(value)
        if match:
            return normalize(value[match.end():])
    return value


def markdown_text(value):
    value = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return normalize(value)


def markdown_units(path):
    units = []
    paragraph = []
    fenced = False
    fence_lines = []

    def flush():
        if paragraph:
            text = markdown_text(" ".join(paragraph))
            if text:
                units.append((text, "text"))
            paragraph.clear()

    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            if fenced:
                text = normalize(" ".join(fence_lines))
                if text:
                    units.append((text, "code"))
                fence_lines.clear()
                fenced = False
            else:
                fenced = True
            continue
        if fenced:
            if stripped:
                fence_lines.append(stripped)
            continue
        if not stripped:
            flush()
            continue
        if re.match(r"^#{1,6}\s+", stripped):
            flush()
            text = markdown_text(re.sub(r"^#{1,6}\s+", "", stripped))
            if text:
                units.append((text, "heading"))
            continue
        if re.match(r"^(?:[-*+] |\d+[.)] )", stripped):
            flush()
            text = markdown_text(re.sub(r"^(?:[-*+] |\d+[.)] )", "", stripped))
            if text:
                paragraph.append(text)
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush()
            cells = [markdown_text(cell) for cell in stripped.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            text = normalize(" | ".join(cell for cell in cells if cell))
            if text:
                units.append((text, "row"))
            continue
        if re.match(r"^<[A-Za-z][^>]*>", stripped):
            flush()
            units.extend(html_fragment_units(stripped))
            continue
        for tag_markup in re.findall(r"<[A-Za-z][^>]*>", stripped):
            units.extend(html_fragment_units(tag_markup))
        paragraph.append(stripped)
    if fenced:
        text = normalize(" ".join(fence_lines))
        if text:
            units.append((text, "code"))
    flush()
    return units


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.hidden_depth = 0
        self.capture = None
        self.units = []

    @staticmethod
    def attributes(attrs):
        values = []
        for name, value in attrs:
            if value and name.lower() in {"alt", "aria-label", "title"}:
                values.append((value, "accessible label"))
        return values

    @classmethod
    def visible_attributes(cls, tag, attrs):
        values = cls.attributes(attrs)
        attrs_dict = {name.lower(): value for name, value in attrs}
        if tag == "input" and (attrs_dict.get("type") or "text").lower() in {
            "button", "email", "reset", "search", "submit", "tel", "text", "url",
        }:
            for name in ("value", "placeholder"):
                if attrs_dict.get(name):
                    values.append((attrs_dict[name], "control"))
        return values

    @staticmethod
    def contextual(tag, attrs):
        if tag == "tr":
            return True
        if tag != "div":
            return False
        classes = next((value or "" for name, value in attrs if name.lower() == "class"), "")
        return bool((CONTEXT_CLASSES | {"brand", "note"}).intersection(classes.split()))

    @staticmethod
    def capture_kind(tag, attrs):
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "heading"
        if tag == "title":
            return "document title"
        if tag == "a":
            return "link"
        if tag in {"button", "label"}:
            return "control"
        if tag == "tr":
            return "row"
        classes = set(next((value or "" for name, value in attrs if name.lower() == "class"), "").split())
        if "brand" in classes:
            return "brand"
        if "note" in classes:
            return "control"
        return "text"

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs}
        node_hidden = (
            tag in HIDDEN_TAGS
            or "hidden" in attrs_dict
        )
        if tag in VOID_TAGS:
            if self.hidden_depth or node_hidden:
                return
            if tag == "meta" and attrs_dict.get("name", "").lower() == "description":
                text = normalize(attrs_dict.get("content", ""))
                if text:
                    self.units.append((text, "text"))
            else:
                for value, kind in self.visible_attributes(tag, attrs):
                    text = normalize(value)
                    if text:
                        if self.capture is None:
                            self.units.append((text, kind))
                        else:
                            self.capture["parts"].append(text)
            return
        self.stack.append((tag, node_hidden))
        if node_hidden:
            self.hidden_depth += 1
        if self.hidden_depth:
            return
        accessible = self.visible_attributes(tag, attrs)
        if self.capture is None:
            for value, kind in accessible:
                text = normalize(value)
                if text:
                    self.units.append((text, kind))
        else:
            self.capture["parts"].extend(value for value, _kind in accessible)
            if self.capture["tag"] == "tr" and tag == "th":
                self.capture["header"] = True
        if self.capture is None and (tag in SEMANTIC_TAGS or self.contextual(tag, attrs)):
            self.capture = {
                "tag": tag, "depth": len(self.stack), "parts": [],
                "kind": self.capture_kind(tag, attrs), "header": False,
            }

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs}
        if (
            self.hidden_depth
            or tag in HIDDEN_TAGS
            or "hidden" in attrs_dict
        ):
            return
        if tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            values = [(attrs_dict.get("content", ""), "text")]
        else:
            values = self.visible_attributes(tag, attrs)
        for value, kind in values:
            text = normalize(value)
            if text:
                if self.capture is None:
                    self.units.append((text, kind))
                else:
                    self.capture["parts"].append(text)

    def handle_data(self, data):
        if self.hidden_depth:
            return
        text = normalize(data)
        if not text:
            return
        if self.capture is None:
            self.units.append((text, "text"))
        else:
            self.capture["parts"].append(text)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self.stack:
            return
        if self.hidden_depth == 0 and self.capture is not None and self.capture["tag"] == tag and self.capture["depth"] == len(self.stack):
            text = normalize(" ".join(self.capture["parts"]))
            if text:
                kind = "column header" if self.capture["header"] else self.capture["kind"]
                self.units.append((text, kind))
            self.capture = None
        _open_tag, node_hidden = self.stack.pop()
        if node_hidden and self.hidden_depth:
            self.hidden_depth -= 1


def html_units(path):
    parser = VisibleHTML()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.units


def html_fragment_units(value):
    parser = VisibleHTML()
    parser.feed(value)
    parser.close()
    return parser.units


def surface_units(path):
    if path.suffix.lower() in {".html", ".htm"}:
        return html_units(path)
    return markdown_units(path)


def pointer_value(document, pointer):
    if pointer == "":
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("pointer must be an RFC 6901 JSON Pointer")
    current = document
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?:[^01]|$)", raw):
            raise ValueError("pointer has an invalid escape")
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"pointer key is absent: {token}")
            current = current[token]
        elif isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError(f"pointer array index is invalid: {token}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"pointer array index is absent: {token}")
            current = current[index]
        else:
            raise ValueError(f"pointer traverses a scalar at: {token}")
    return current


def relative_evidence(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("evidence path must be a nonempty relative string")
    candidate = pathlib.PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("evidence path must stay inside the evidence root")
    if value != "room.json" and (not candidate.parts or candidate.parts[0] != "evidence"):
        raise ValueError("evidence path must be room.json or live under evidence/")
    resolved = (root / pathlib.Path(*candidate.parts)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("evidence path escapes the evidence root") from error
    return resolved


def fail(errors):
    for error in errors:
        print(error)
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=pathlib.Path)
    parser.add_argument("--allow-absent", action="store_true")
    parser.add_argument("matrix", type=pathlib.Path)
    parser.add_argument("surfaces", nargs="+", type=pathlib.Path)
    args = parser.parse_args()

    errors = []
    root = args.evidence_root.resolve()
    matrix_path = args.matrix.resolve()
    surface_paths = [path.resolve() for path in args.surfaces]
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return fail([f"invalid public-claims matrix: {error}"])
    if not isinstance(matrix, dict):
        return fail(["invalid public-claims matrix: root must be an object"])
    technologies = matrix.get("technology_terms")
    if not isinstance(technologies, list) or any(not isinstance(term, str) or not normalize(term) for term in technologies):
        errors.append("invalid technology_terms: expected nonempty strings")
    elif len({normalize(term) for term in technologies}) != len(technologies):
        errors.append("invalid technology_terms: duplicate normalized term")
    claims = matrix.get("claims")
    if not isinstance(claims, list):
        return fail(errors + ["invalid claims: expected a list"])

    observed = []
    for path in surface_paths:
        try:
            units = surface_units(path)
        except (OSError, UnicodeError) as error:
            errors.append(f"could not read public surface {path}: {error}")
            continue
        observed.extend((path, text, kind) for text, kind in units)

    kinds_by_text = {}
    for _path, text, kind in observed:
        kinds_by_text.setdefault(text, set()).add(kind)

    rows = {}
    used_pointers = set()
    forbidden_evidence = {matrix_path, *surface_paths}
    for index, claim in enumerate(claims):
        label = f"claim {index + 1}"
        if not isinstance(claim, dict):
            errors.append(f"invalid {label}: expected an object")
            continue
        text = normalize(claim.get("text", ""))
        status = claim.get("status")
        evidence = claim.get("evidence")
        if not text:
            errors.append(f"invalid {label}: text must be nonempty")
            continue
        if text in rows:
            errors.append(f"duplicate public-claims text: {text}")
            continue
        rows[text] = claim
        if status not in STATUSES:
            errors.append(f"invalid status for {text}: {status}")
            continue
        if not isinstance(evidence, list):
            errors.append(f"invalid evidence list for {text}")
            continue
        if status == "VERIFIED":
            if not evidence:
                errors.append(f"verified claim has no evidence: {text}")
            required_clauses = claim_clauses(text)
            covered_clauses = set()
            locator_words_by_clause = {clause: set() for clause in required_clauses}
            for evidence_index, item in enumerate(evidence):
                prefix = f"evidence {evidence_index + 1} for {text}"
                if not isinstance(item, dict):
                    errors.append(f"invalid {prefix}: expected an object")
                    continue
                if set(item) != {"path", "pointer", "equals", "display", "clause"}:
                    errors.append(f"invalid {prefix}: expected path, pointer, equals, display and clause")
                    continue
                clause = normalize(item["clause"]).strip(" .,!?:")
                if clause not in required_clauses:
                    errors.append(f"evidence clause is not an atomic clause from the public text in {prefix}")
                else:
                    covered_clauses.add(clause)
                try:
                    target = relative_evidence(root, item["path"])
                except ValueError as error:
                    errors.append(f"invalid {prefix}: {error}")
                    continue
                if target in forbidden_evidence:
                    errors.append(f"invalid {prefix}: public surfaces and the matrix cannot certify claims")
                    continue
                if target.suffix.lower() != ".json":
                    errors.append(f"invalid {prefix}: evidence target must be JSON")
                    continue
                pointer_key = (target, item["pointer"] if isinstance(item["pointer"], str) else None)
                if pointer_key in used_pointers:
                    errors.append(f"reused evidence pointer in {prefix}")
                    continue
                used_pointers.add(pointer_key)
                try:
                    document = json.loads(target.read_text(encoding="utf-8"))
                    actual = pointer_value(document, item["pointer"])
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                    errors.append(f"invalid {prefix}: {error}")
                    continue
                structured_words = set()
                structured_measure_words = set()
                if item["path"] != "room.json":
                    pointer_match = re.fullmatch(r"/measurements/(0|[1-9][0-9]*)/value", item["pointer"])
                    if item["path"] != "evidence/facts.json" or pointer_match is None:
                        errors.append(
                            f"non-room evidence must resolve a source-bound measurement value in {prefix}"
                        )
                        continue
                    record_pointer = item["pointer"].rsplit("/", 1)[0]
                    try:
                        record = pointer_value(document, record_pointer)
                    except ValueError as error:
                        errors.append(f"invalid measurement record in {prefix}: {error}")
                        continue
                    if not isinstance(record, dict) or set(record) != MEASUREMENT_KEYS:
                        errors.append(f"measurement record has the wrong fields in {prefix}")
                        continue
                    if record.get("value") != actual or type(record.get("value")) is not type(actual):
                        errors.append(f"measurement record value does not match its pointer in {prefix}")
                        continue
                    metadata = [record.get(name) for name in ("entity", "predicate", "measure")]
                    if any(not isinstance(value, str) or not normalize(value) for value in metadata):
                        errors.append(f"measurement entity, predicate and measure must be nonempty strings in {prefix}")
                        continue
                    if any(len(words(value)) > 4 for value in metadata):
                        errors.append(f"measurement metadata must stay atomic in {prefix}")
                        continue
                    source = record.get("source")
                    if not isinstance(source, dict) or set(source) != MEASUREMENT_SOURCE_KEYS:
                        errors.append(f"measurement source has the wrong fields in {prefix}")
                        continue
                    try:
                        source_target = relative_evidence(root, source.get("path"))
                    except ValueError as error:
                        errors.append(f"invalid measurement source in {prefix}: {error}")
                        continue
                    if source.get("path") not in APPROVED_RAW_EVIDENCE or source_target in forbidden_evidence:
                        errors.append(f"measurement source is not an approved raw evidence file in {prefix}")
                        continue
                    try:
                        source_document = json.loads(source_target.read_text(encoding="utf-8"))
                        source_actual = pointer_value(source_document, source.get("pointer"))
                    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                        errors.append(f"invalid raw measurement source in {prefix}: {error}")
                        continue
                    if type(source_actual) is not type(actual) or source_actual != actual:
                        errors.append(f"measurement value differs from its raw source in {prefix}")
                        continue
                    structured_words = set().union(*(words(value) for value in metadata))
                    structured_measure_words = words(record["measure"])
                    raw_segments = source.get("pointer").strip("/").split("/")
                    raw_leaf_words = words(raw_segments[-1]) if raw_segments else set()
                    raw_parent_words = set().union(*(words(segment) for segment in raw_segments[:-1]))
                    significant_parent_words = set()
                    for segment_index, segment in enumerate(raw_segments[:-1]):
                        segment_words = words(segment)
                        next_segment = raw_segments[segment_index + 1]
                        if segment_words.issubset(RAW_SOURCE_QUALIFIERS):
                            continue
                        if next_segment.isdigit() and segment_words.issubset(RAW_COLLECTION_QUALIFIERS):
                            continue
                        significant_parent_words.update(segment_words)
                    raw_pointer_words = raw_leaf_words | raw_parent_words
                    raw_source_words = raw_pointer_words | words(source_actual)
                    unbound_metadata = structured_words - raw_source_words
                    if unbound_metadata:
                        errors.append(
                            f"measurement metadata is absent from its raw source in {prefix}: "
                            f"{sorted(unbound_metadata)}"
                        )
                        continue
                    explained_raw = structured_words | words(clause)
                    leaf_qualifiers = RAW_LEAF_QUALIFIERS | (
                        {"content", "quote"} if isinstance(source_actual, str) else set()
                    )
                    unexplained_raw = (
                        (raw_leaf_words - explained_raw - leaf_qualifiers)
                        | (significant_parent_words
                           - explained_raw
                           - GENERIC_EVIDENCE_WORDS
                          )
                    )
                    if unexplained_raw:
                        errors.append(
                            f"raw source locator adds semantics absent from its measurement and clause in {prefix}: "
                            f"{sorted(unexplained_raw)}"
                        )
                        continue
                expected = item["equals"]
                if type(actual) is not type(expected) or actual != expected:
                    errors.append(f"typed evidence mismatch in {prefix}")
                display = normalize(item["display"])
                if not display or display not in clause:
                    errors.append(f"evidence display is absent from its atomic clause in {prefix}")
                exact_assertion = False
                if isinstance(actual, str):
                    normalized_actual = normalize(actual)
                    exact_assertion = normalized_actual.strip(" .,!?:") == clause
                    if exact_assertion and item["path"] != "room.json":
                        errors.append(f"exact public text is circular evidence outside room.json in {prefix}")
                    elif not exact_assertion and display != normalized_actual:
                        errors.append(
                            f"partial string evidence must display the complete resolved scalar in {prefix}"
                        )
                elif isinstance(actual, (dict, list)):
                    errors.append(f"evidence pointer must resolve to a JSON scalar in {prefix}")
                elif display != json.dumps(actual, ensure_ascii=False, separators=(",", ":")):
                    errors.append(f"evidence display does not equal the resolved scalar in {prefix}")
                locator_words = (
                    evidence_words(item["path"], item["pointer"], actual, text)
                    if item["path"] == "room.json" else structured_words
                )
                if clause in locator_words_by_clause:
                    locator_words_by_clause[clause].update(
                        locator_words | (words(actual) if item["path"] == "room.json" or not exact_assertion else set())
                    )
                pointer_words = words(str(item["pointer"])) - GENERIC_EVIDENCE_WORDS
                if not isinstance(actual, str):
                    scalar_locator_words = structured_measure_words or {
                        word for word in pointer_words if any(char.isalpha() for char in word)
                    }
                    unexplained = scalar_locator_words - words(clause) - LOCATOR_QUALIFIERS
                    if unexplained:
                        errors.append(
                            f"scalar evidence locator adds a dimension absent from its atomic clause in {prefix}: "
                            f"{sorted(unexplained)}"
                        )
                polarity = (pointer_words | words(actual)) & POLARITY_WORDS
                missing_polarity = polarity - words(clause)
                if missing_polarity:
                    errors.append(
                        f"evidence polarity is absent from its atomic clause in {prefix}: {sorted(missing_polarity)}"
                    )
                technology_words = {
                    word for term in technologies if isinstance(term, str) for word in words(term)
                } if isinstance(technologies, list) else set()
                clause_predicates = {
                    word for word in words(clause) - technology_words - LOW_INFORMATION_WORDS - GENERIC_EVIDENCE_WORDS
                    if any(char.isalpha() for char in word)
                }
                locator_predicates = {
                    word for word in (
                    locator_words | (words(actual) if item["path"] == "room.json" or not exact_assertion else set())
                    - technology_words - LOW_INFORMATION_WORDS - GENERIC_EVIDENCE_WORDS
                    ) if any(char.isalpha() for char in word)
                }
                if not clause_predicates or not clause_predicates.issubset(locator_predicates):
                    missing_predicates = sorted(clause_predicates - locator_predicates)
                    errors.append(
                        f"evidence locator does not cover every semantic field in its atomic clause in {prefix}: "
                        f"{missing_predicates}"
                    )
            if set(required_clauses) != covered_clauses:
                missing = sorted(set(required_clauses) - covered_clauses)
                errors.append(f"verified claim has unsupported atomic clauses: {text}: {missing}")
            for clause in required_clauses:
                for term in technologies if isinstance(technologies, list) else []:
                    normalized_term = normalize(term)
                    if re.search(
                        rf"(?<![A-Za-z0-9]){re.escape(normalized_term)}(?![A-Za-z0-9])",
                        clause,
                        re.IGNORECASE,
                    ) and not words(normalized_term).issubset(locator_words_by_clause.get(clause, set())):
                        errors.append(
                            f"technology named in a verified clause is absent from its evidence locator: "
                            f"{clause}: {normalized_term}"
                        )
                displays = [
                    normalize(item.get("display", ""))
                    for item in evidence if normalize(item.get("clause", "")).strip(" .,!?:") == clause
                ]
                for number in re.findall(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?[kKmMbB]?(?:/\d[\d,]*)?(?![A-Za-z0-9])", clause):
                    compact = number.replace(",", "")
                    if not any(compact in display.replace(",", "") for display in displays):
                        errors.append(f"numeric assertion has no evidence display in clause: {clause}: {number}")
        elif status == "UNKNOWN DISCLOSED":
            if evidence:
                errors.append(f"unknown claim must not carry evidence: {text}")
            entity = normalize(claim.get("entity", ""))
            metric = normalize(claim.get("metric", ""))
            state = normalize(claim.get("state", ""))
            approved_entities = {
                normalize(term) for term in technologies
                if isinstance(term, str) and ENTITY_RE.fullmatch(normalize(term))
            } if isinstance(technologies, list) else set()
            if (
                entity not in approved_entities
                or metric not in UNKNOWN_METRICS
                or state not in UNKNOWN_STATES
                or text != f"{entity} {metric} {state}."
            ):
                errors.append(f"unknown disclosure must reconstruct one approved entity metric sentence: {text}")
        elif status == "NONCLAIM":
            if evidence:
                errors.append(f"non-claim must not carry evidence: {text}")
            reason = normalize(claim.get("reason", ""))
            if reason not in NONCLAIM_REASONS:
                errors.append(f"non-claim reason must be an approved category: {text}")
            elif not kinds_by_text.get(text) or not kinds_by_text[text].issubset(NONCLAIM_KINDS[reason]):
                errors.append(f"non-claim category does not match the public source structure: {text}: {reason}")
            elif reason in {"document title", "heading"} and not words(text).issubset(NEUTRAL_HEADING_WORDS):
                errors.append(f"non-claim heading is not in the neutral structure vocabulary: {text}")
            technology_hit = any(
                re.search(rf"(?<![A-Za-z0-9]){re.escape(normalize(term))}(?![A-Za-z0-9])", text, re.IGNORECASE)
                for term in technologies if isinstance(term, str) and normalize(term)
            ) if isinstance(technologies, list) else False
            if reason == "command":
                if not COMMAND_RE.fullmatch(text):
                    errors.append(f"non-claim command does not match an approved command shape: {text}")
                else:
                    payload = command_payload(text)
                    payload_technology_hit = any(
                        re.search(
                            rf"(?<![A-Za-z0-9]){re.escape(normalize(term))}(?![A-Za-z0-9])",
                            payload,
                            re.IGNORECASE,
                        )
                        for term in technologies if isinstance(term, str) and normalize(term)
                    ) if isinstance(technologies, list) else False
                    if CLAIM_LIKE_RE.search(payload) or payload_technology_hit:
                        errors.append(f"claim-like command payload needs evidence: {text}")
            elif (
                CLAIM_LIKE_RE.search(text)
                or CLAIM_QUALIFIER_RE.search(text)
                or QUANTIFIER_RE.search(text)
                or technology_hit
            ):
                errors.append(f"claim-like text cannot use this non-claim category: {text}")
        elif status == "CUT" and evidence:
            errors.append(f"cut claim must not carry evidence: {text}")

    observed_text = {unit for _, unit, _kind in observed}
    for path, unit, _kind in observed:
        claim = rows.get(unit)
        if claim is None:
            errors.append(f"unmapped public claim in {path}: {unit}")
        elif claim.get("status") == "CUT":
            errors.append(f"CUT claim is still public in {path}: {unit}")
    if not args.allow_absent:
        for text, claim in rows.items():
            if claim.get("status") != "CUT" and text not in observed_text:
                errors.append(f"matrix row is absent from strict public surfaces: {text}")
    if errors:
        return fail(errors)
    print(
        f"PASS  {len(observed)} public text occurrences map to {len(rows)} reviewed rows "
        f"across {len(surface_paths)} public surfaces"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
