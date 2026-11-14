import json, hashlib

from .dataset import Record, Dataset,_generate_version


class DatasetError(ValueError):
    """Raised when dataset validation fails."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)

        displayed = errors[:10]
        message = "Dataset validation failed:\n" + "\n".join(
            f"  - {error}" for error in displayed
        )

        if len(errors) > 10:
            message += f"\n  - ... and {len(errors) - 10} more error(s)"

        super().__init__(message)

def _generate_id(inputs: dict) -> str:
    """Generate a stable ID from canonical JSON inputs."""
    canonical = json.dumps(
        inputs,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"c-{digest[:8]}"


def load_jsonlfile(path):
    records =[]
    allowed_keys = {
        "id",
        "inputs",
        "expectations",
        "tags",
        "metadata"
    }
    errors = []
    seen_ids={}
    try:
        file = path.open("r", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DatasetError([f"cannot read {path}: {exc}"]) from exc
    
    with file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
                continue
            
            if not isinstance(record, dict):
                errors.append(f"line {line_number}: record must be a JSON object")
                continue

            line_errors = []

            for key in sorted(set(record) - allowed_keys):
                line_errors.append(f'"{key}" is an unknown top-level key')
            
            if "inputs" not in record:
                line_errors.append('"inputs" is required')
            elif not isinstance(record["inputs"], dict):
                line_errors.append('"inputs" must be an object')
            
            record_id = record.get("id")
            if record_id is not None:
                if not isinstance(record_id, str) or not record_id.strip():
                    line_errors.append('"id" must be a non-empty string')
                    record_id = None
            elif isinstance(record.get("inputs"), dict):
                try:
                    record_id = _generate_id(record["inputs"])
                except (TypeError, ValueError) as exc:
                    line_errors.append(
                        f'cannot generate id from "inputs": {exc}'
                    )
            
            expectations = record.get("expectations", {})
            if not isinstance(expectations, dict):
                line_errors.append('"expectations" must be an object')

            tags = record.get("tags", [])
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) for tag in tags
            ):
                line_errors.append('"tags" must be an array of strings')

            metadata = record.get("metadata", {})
            if not isinstance(metadata, dict):
                line_errors.append('"metadata" must be an object')
            
            if record_id is not None:
                if record_id in seen_ids:
                    line_errors.append(
                        f'duplicate id "{record_id}" '
                        f'(first defined on line {seen_ids[record_id]})'
                    )
                else:
                    seen_ids[record_id] = line_number
            
            errors.extend(f"line {line_number}: {error}"for error in line_errors)

            if line_errors:
                continue

            records.append(Record(id=record_id,inputs= record['inputs'],expectations=expectations,tags=tuple(tags),metadata=metadata))
        if errors:
            raise DatasetError(errors)

    return records

def load_dataset(path,name) -> "Dataset":
    records = load_jsonlfile(path=path)
    records = tuple(records)
    version = _generate_version(tuple(records))
    return Dataset(name,records=records,version=version)

