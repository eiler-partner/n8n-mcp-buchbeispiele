"""Validate one document response against JSON Schema Draft 2020-12."""

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from jsonschema import Draft202012Validator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="for example http://127.0.0.1:8080/documents/doc-1")
    args = parser.parse_args()
    schema_path = Path(__file__).with_name("document.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    with urlopen(args.url, timeout=5) as response:
        document = json.load(response)
    Draft202012Validator(schema).validate(document)
    print(f"Schema OK: {document['id']} (Version {document['version']})")


if __name__ == "__main__":
    main()
