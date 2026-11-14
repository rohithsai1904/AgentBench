from dataclasses import dataclass, field
from typing import Any, Mapping
import random, json,hashlib
from pathlib import Path


@dataclass(frozen=True)
class Record:
    """A single evaluation record.

    `id` is the primary identity. `key` is a stable shorthand derived from
    `inputs` and is not a separate identity.
    """

    id: str
    inputs: Mapping[str, Any]
    expectations: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Dataset:
    """A collection of evaluation records."""

    name: str
    records: tuple[Record, ...]
    version: str

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def get_record(self, record_id: str) -> Record:
        for record in self.records:
            if record.id == record_id:
                return record

        raise KeyError(f"Record not found: {record_id}")

    def filter(self, tag: str) -> "Dataset":
        """Return a dataset containing records with the specified tag."""
        filtered_records = tuple(
            record for record in self.records if tag in record.tags
        )

        return Dataset(
            name=self.name,
            records=filtered_records,
            version=self.version,
        )

    def sample(self, n: int, seed: int) -> "Dataset":
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError("n must be a non-negative integer")

        if n > len(self.records):
            raise ValueError(
                f"cannot sample {n} records from a dataset "
                f"containing {len(self.records)} records"
            )

        rng = random.Random(seed)
        selected_indices = set(rng.sample(range(len(self.records)), n))

        sampled_records = tuple(
            record
            for index, record in enumerate(self.records)
            if index in selected_indices
        )

        return Dataset(
            name=self.name,
            records=sampled_records,
            version=self.version,
        )

    def to_jsonl(self, path: str) -> None:
        """Write the dataset to a UTF-8 JSONL file."""
        path = Path(path)

        with path.open("w", encoding="utf-8", newline="\n") as file:
            for record in self.records:
                payload = {
                    "id": record.id,
                    "inputs": record.inputs,
                    "expectations": record.expectations,
                    "tags": list(record.tags),
                    "metadata": record.metadata,
                }

                file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                file.write("\n")
    
    def to_payload(self) -> list[dict]:
        return [
            {
                "id": record.id,
                "inputs": record.inputs,
                "expectations": record.expectations,
                "tags": list(record.tags),
                "metadata": record.metadata
            }
            for record in self.records
        ]
        
    def add_records(self, records: list[Record]) -> "Dataset":
        """Return a new dataset with validated records."""

        if not records:
            return self

        errors = []
        seen_ids = {record.id for record in self.records}

        for index, record in enumerate(records):
            try:
                _validate_record(record)
            except (TypeError, ValueError) as exc:
                errors.append(f"record at index {index}: {exc}")
                continue

            if record.id in seen_ids:
                errors.append(
                    f'duplicate record id "{record.id}"'
                )
            else:
                seen_ids.add(record.id)

        if errors:
            raise ValueError(
                "Record validation failed:\n"
                + "\n".join(f"  - {error}" for error in errors)
            )

        updated_records = self.records + tuple(records)

        version = _generate_version(updated_records)

        return Dataset(
            name=self.name,
            records=updated_records,
            version=version,
        )


def _validate_record(record: Record) -> None:
    """Validate a Record before adding it to a dataset."""

    if not isinstance(record, Record):
        raise TypeError("record must be a Record instance")

    if not isinstance(record.id, str) or not record.id.strip():
        raise ValueError("record id must be a non-empty string")

    if not isinstance(record.inputs, Mapping):
        raise ValueError(f'record "{record.id}": inputs must be an object')

    if not isinstance(record.expectations, Mapping):
        raise ValueError(
            f'record "{record.id}": expectations must be an object'
        )

    if not isinstance(record.tags, tuple) or not all(
        isinstance(tag, str) for tag in record.tags
    ):
        raise ValueError(
            f'record "{record.id}": tags must be a tuple of strings'
        )

    if not isinstance(record.metadata, Mapping):
        raise ValueError(f'record "{record.id}": metadata must be an object')


def _generate_version(records: tuple[Record, ...]) -> str:
    """Generate an order-independent version hash for a dataset."""

    canonical_cases = [
        {
            "id": record.id,
            "inputs": record.inputs,
            "expectations": record.expectations,
            "tags": list(record.tags),
            "metadata": record.metadata,
        }
        for record in sorted(records, key=lambda record: record.id)
    ]

    canonical = json.dumps(
        canonical_cases,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return digest[:12]