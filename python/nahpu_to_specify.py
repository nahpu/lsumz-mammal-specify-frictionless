"""Convert a NAHPU Data Package into an LSUMZ Mammalogy Specify WorkBench sheet.

The input is a NAHPU Data Package (Frictionless) exported from NAHPU's
`Bundle records`: the `.zip` or `.tar.gz` archive, its extracted folder, or
its `datapackage.json`. The output is a CSV with one row per mammal specimen,
in the column layout of the LSUMZ Mammalogy incoming-data sheet.

Usage:
    python python/nahpu_to_specify.py INPUT [-o OUTPUT] [--all-taxa]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tarfile
import tempfile
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from frictionless import Package

ROOT = Path(__file__).resolve().parent.parent
CONTINENTS = ROOT / "data" / "country-continent.csv"

MAMMAL_GROUPS = {"Mammals", "General Mammals", "Bats"}

# Columns before and after the numbered preparation groups. Remarks sits after
# the second group, where the LSUMZ sheet places it.
LEADING_COLUMNS = [
    "Catalog Number", "Class", "Order", "Family", "Genus", "Species", "Sex",
    "Continent", "Country", "State", "County", "Locality Name", "Elevation",
    "Elevation Unit", "Collector1LastName", "Field Number", "Start Date",
]
TRAILING_COLUMNS = [
    "Latitude", "Longitude", "MaxErrorDistance", "OtherCollection OtherCollNumber",
    "Total Length", "TailLength", "HFLength", "Ear", "Weight",
]
REMARKS_AFTER_GROUP = 2

# Measurements written in brackets when the accuracy note matches, as in
# NAHPU's bundled LSUMZ-mammalogy export preset.
BRACKET_RULES = {
    "totalLength": ("Tail cropped", "Other reason", "Partially eaten"),
    "tailLength": ("Tail cropped", "Partially eaten", "Other reason"),
    "earLength": ("Ear damaged", "Other reason"),
    "hindFootLength": ("hindFootLength", "Partially eaten"),
}

LAST_NAME_FIRST = re.compile(r"^([^,]*[^\s,])\s+([^\s,]+)$")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    with open_package(args.input) as package:
        rows, warnings = convert(package, all_taxa=args.all_taxa)
    output = args.output or ROOT / "results" / f"{_stem(args.input)}-specify.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(rows, output)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"Wrote {len(rows)} specimens to {output}")
    return 0


@contextmanager
def open_package(path: Path) -> Iterator[Package]:
    """Yields the Frictionless package at [path], extracting archives first."""
    path = Path(path)
    if path.is_dir():
        yield Package(str(path / "datapackage.json"))
        return
    if path.name == "datapackage.json":
        yield Package(str(path))
        return
    with tempfile.TemporaryDirectory(prefix="nahpu-dp-") as tmp:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                archive.extractall(tmp)
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                archive.extractall(tmp, filter="data")
        else:
            raise ValueError(f"Not a NAHPU Data Package: {path}")
        yield Package(str(Path(tmp) / "datapackage.json"))


def convert(package: Package, all_taxa: bool = False) -> tuple[list[dict], list[str]]:
    """Builds one LSUMZ sheet row per specimen in [package]."""
    warnings: list[str] = []
    specimens = _read(package, "specimen")
    if not all_taxa:
        specimens = [s for s in specimens if s["taxonGroup"] in MAMMAL_GROUPS]

    taxa = _index(_read(package, "taxonomy"), "id")
    attributes = _index(_read(package, "mammalattribute"), "specimenUuid")
    personnel = _index(_read(package, "personnel"), "uuid")
    events = _index(_read(package, "collevent"), "id")
    sites = _index(_read(package, "site"), "id")
    geography = _index(_read(package, "geography"), "id")
    coordinates = _read(package, "coordinate")
    coordinates_by_id = _index(coordinates, "id")
    coordinates_by_site: dict[Any, list[dict]] = defaultdict(list)
    for coordinate in coordinates:
        coordinates_by_site[coordinate["siteID"]].append(coordinate)
    parts: dict[str, list[dict]] = defaultdict(list)
    for part in sorted(_read(package, "specimenpart"), key=lambda p: p["id"]):
        parts[part["specimenUuid"]].append(part)
    sex_labels = {
        int(row["sqlite_index"]): row["display_name"]
        for row in _read(package, "sqlite-enum-mappings")
        if row["table"] == "mammalAttribute" and row["column"] == "sex"
    }
    continents = _read_continents()

    group_count = max((len(parts[s["uuid"]]) for s in specimens), default=0)
    rows = []
    for specimen in sorted(specimens, key=_specimen_order):
        taxon = taxa.get(specimen["speciesID"], {})
        attribute = attributes.get(specimen["uuid"], {})
        event = events.get(specimen["collEventID"], {})
        site = sites.get(event.get("siteID"), {})
        place = geography.get(site.get("geographyId"), {})
        coordinate = coordinates_by_id.get(specimen["coordinateID"])
        if coordinate is None:
            # NAHPU falls back to the event site's only coordinate.
            candidates = coordinates_by_site.get(event.get("siteID"), [])
            coordinate = candidates[0] if len(candidates) == 1 else {}
        country = _text(place.get("country"))
        continent = continents.get(country.casefold(), "")
        if country and not continent:
            warnings.append(f"No continent for country '{country}'.")
        elevation = _number(coordinate.get("elevationInMeter"))
        sex = attribute.get("sex")

        row = {
            "Catalog Number": _text(specimen["museumID"]),
            "Class": _text(taxon.get("taxonClass")),
            "Order": _text(taxon.get("taxonOrder")),
            "Family": _text(taxon.get("taxonFamily")),
            "Genus": _text(taxon.get("genus")),
            "Species": _text(taxon.get("specificEpithet")),
            "Sex": sex_labels.get(sex, _text(sex)),
            "Continent": continent,
            "Country": country,
            "State": _text(place.get("stateProvince")),
            "County": _text(place.get("county")),
            "Locality Name": "; ".join(
                value
                for value in (_text(place.get("municipality")), _text(place.get("locality")))
                if value
            ),
            "Elevation": elevation,
            "Elevation Unit": "m" if elevation else "",
            "Collector1LastName": last_name_first(
                _text(personnel.get(specimen["catalogerID"], {}).get("name"))
            ),
            "Field Number": _number(
                specimen["fieldNumber"]
                if specimen["fieldNumber"] is not None
                else specimen["projectFieldNumber"]
            ),
            "Start Date": format_date(specimen["collectionDate"]),
            "Remarks": _text(attribute.get("remark")),
            "Latitude": _number(coordinate.get("decimalLatitude")),
            "Longitude": _number(coordinate.get("decimalLongitude")),
            "MaxErrorDistance": _number(coordinate.get("uncertaintyInMeters")),
            "OtherCollection OtherCollNumber": "",
            "Total Length": _measurement(attribute, "totalLength"),
            "TailLength": _measurement(attribute, "tailLength"),
            "HFLength": _measurement(attribute, "hindFootLength"),
            "Ear": _measurement(attribute, "earLength"),
            "Weight": _measurement(attribute, "weight"),
        }
        for index, part in enumerate(parts[specimen["uuid"]], start=1):
            row[f"PrepType{index}"] = _text(part["type"])
            row[f"PrepType{index}Count"] = _text(part["count"])
            row[f"PrepType{index}Location"] = _text(part["storageLocation"])
        rows.append(row)
    return [_complete(row, group_count) for row in rows], warnings


def columns(group_count: int) -> list[str]:
    """The sheet's header for [group_count] preparation groups."""
    header = list(LEADING_COLUMNS)
    for index in range(1, group_count + 1):
        header += [f"PrepType{index}", f"PrepType{index}Count", f"PrepType{index}Location"]
        if index == REMARKS_AFTER_GROUP:
            header.append("Remarks")
    if group_count < REMARKS_AFTER_GROUP:
        header.append("Remarks")
    return header + TRAILING_COLUMNS


def write_csv(rows: list[dict], path: Path) -> None:
    group_count = max(
        (int(k[8:]) for row in rows for k in row if re.fullmatch(r"PrepType\d+", k)),
        default=0,
    )
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns(group_count), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def last_name_first(name: str) -> str:
    """`Heru Handika` -> `Handika, Heru`; names with a comma are kept."""
    return LAST_NAME_FIRST.sub(r"\2, \1", name)


def format_date(value: Any) -> str:
    """ISO `2016-02-17` -> `17/02/2016`; anything else is kept as text."""
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = _text(value)
    try:
        return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return text


def _complete(row: dict, group_count: int) -> dict:
    return {column: row.get(column, "") for column in columns(group_count)}


def _measurement(attribute: dict, field: str) -> str:
    value = _number(attribute.get(field))
    if not value:
        return value
    accuracy = _text(attribute.get("accuracy"))
    if field == "weight":
        bracket = bool(accuracy) and accuracy != "Accurate"
    else:
        bracket = any(note in accuracy for note in BRACKET_RULES.get(field, ()))
    return f"[{value}]" if bracket else value


def _number(value: Any) -> str:
    """Writes numbers without a trailing `.0`, as NAHPU's exports do."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value)
    return text[:-2] if re.fullmatch(r"-?\d+\.0", text) else text


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _read(package: Package, name: str) -> list[dict]:
    # Empty NAHPU tables are left out of the package, so a missing resource is
    # an empty table.
    if not package.has_resource(name):
        return []
    return [row.to_dict() for row in package.get_resource(name).read_rows()]


def _index(rows: list[dict], key: str) -> dict:
    return {row[key]: row for row in rows}


def _read_continents() -> dict[str, str]:
    with open(CONTINENTS, newline="", encoding="utf-8") as handle:
        return {row["country"].casefold(): row["continent"] for row in csv.DictReader(handle)}


def _specimen_order(specimen: dict) -> tuple:
    number = specimen["fieldNumber"]
    if number is None:
        number = specimen["projectFieldNumber"]
    return (specimen["catalogerID"] or "", number is None, number or 0, specimen["uuid"])


def _stem(path: Path) -> str:
    name = Path(path).name
    if name == "datapackage.json":
        name = Path(path).parent.name
    for suffix in (".tar.gz", ".zip", ".tgz"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.removesuffix(".nahpu-dp")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=ROOT / "data" / "example" / "ambang-shrews.nahpu-dp.zip",
        help="NAHPU Data Package archive, folder, or datapackage.json",
    )
    parser.add_argument("-o", "--output", type=Path, help="output CSV path")
    parser.add_argument(
        "--all-taxa",
        action="store_true",
        help="include every specimen, not only mammals",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
