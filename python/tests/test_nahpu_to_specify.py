import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import nahpu_to_specify as converter  # noqa: E402

EXAMPLE = HERE.parent.parent / "data" / "example"


def read(path: Path) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def test_example_matches_lsumz_sheet(tmp_path: Path) -> None:
    output = tmp_path / "specify.csv"

    converter.main([str(EXAMPLE / "ambang-shrews.nahpu-dp.zip"), "-o", str(output)])

    assert read(output) == read(EXAMPLE / "expected-specify.csv")


def test_reads_an_extracted_package(tmp_path: Path) -> None:
    import zipfile

    with zipfile.ZipFile(EXAMPLE / "ambang-shrews.nahpu-dp.zip") as archive:
        archive.extractall(tmp_path / "package")
    output = tmp_path / "specify.csv"

    converter.main([str(tmp_path / "package"), "-o", str(output)])

    assert read(output) == read(EXAMPLE / "expected-specify.csv")


def test_formats_names_dates_and_brackets() -> None:
    assert converter.last_name_first("Heru Handika") == "Handika, Heru"
    assert converter.last_name_first("Mary Ann Smith") == "Smith, Mary Ann"
    assert converter.last_name_first("Handika, Heru") == "Handika, Heru"
    assert converter.format_date("2016-02-17") == "17/02/2016"
    assert converter.format_date("") == ""
    eaten = {"accuracy": "Partially eaten", "totalLength": 150.0, "weight": 12.5}
    assert converter._measurement(eaten, "totalLength") == "[150]"
    assert converter._measurement(eaten, "weight") == "[12.5]"
    assert converter._measurement({"accuracy": "Accurate", "weight": 12.5}, "weight") == "12.5"


def test_remarks_follow_the_second_preparation_group() -> None:
    header = converter.columns(3)
    assert header.index("Remarks") == header.index("PrepType2Location") + 1
    assert converter.columns(0)[17] == "Remarks"
