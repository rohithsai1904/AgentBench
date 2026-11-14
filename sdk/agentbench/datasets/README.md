
# Dataset Format

Datasets use JSON Lines (`.jsonl`) format.

## File Rules

- UTF-8 encoding.
- One JSON object per line.
- Blank lines are ignored.
- Comments are not allowed.
- Each non-blank line must contain a valid JSON object.

## Record Schema

Each record supports the following top-level fields:

| Field | Required | Type |
|---|---|---|
| `inputs` | Yes | Object |
| `id` | No | String (primary identity) |
| `expectations` | No | Object |
| `tags` | No | Array of strings |
| `metadata` | No | Object |

Unknown top-level keys are validation errors. This catches misspellings such as `expected` instead of `expectations`.

`inputs` must always be a JSON object.

## Identity

`id` is the primary identity of a record. Duplicate `id` values in a dataset are validation errors.


1. Serialize `inputs` as canonical JSON with sorted keys and no unnecessary whitespace.
2. Encode the serialized JSON as UTF-8.
3. Calculate its SHA-256 hash.
4. Take the first 8 hexadecimal characters.
5. Prefix the result with `c-`.

Example: `c-a1b2c3d4`

Generated IDs are independent of line position. Identical inputs produce identical IDs.

Explicit IDs take precedence over generated IDs.

## Optional Fields

- `expectations`: Expected evaluator outcomes, represented as an object.
- `tags`: Labels used for filtering and grouping.
- `metadata`: Additional dataset information, represented as an object.

If omitted, optional fields remain absent; they are not inferred from other fields.

## Validation

A record is invalid if:

- It is not a JSON object.
- `inputs` is missing.
- `inputs` is not an object.
- An unknown top-level key is present.
- An optional field has an invalid type.
- The line contains malformed JSON.

Validation errors should identify the file and line number.

## Example

```json
{"id":"refund-001","inputs":{"message":"Headphones arrived broken","order_id":"A-1001"},"expectations":{"action":"refund"},"tags":["refund"],"metadata":{"source":"manual"}}
```