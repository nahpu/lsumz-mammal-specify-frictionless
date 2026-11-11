"""Tutorial 3 example: reshape a NAHPU Data Package into a field catalog.

Each row is one specimen with its field ID, name, sex, place, date, and parts.
Run from the repository root:

    uv run --project python python python/examples/field_catalog.py
"""

from pathlib import Path
import zipfile

import pandas as pd
from frictionless import Package

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "data" / "example" / "ambang-shrews.nahpu-dp.zip"
EXTRACTED = ROOT / "data" / "extracted" / "ambang-shrews"
OUTPUT = ROOT / "results" / "ambang-shrews-field-catalog.csv"

# 1. Extract the archive and open the package.
with zipfile.ZipFile(ARCHIVE) as archive:
    archive.extractall(EXTRACTED)
package = Package(EXTRACTED / "datapackage.json")
print(package.resource_names)


# 2. Read a table into a data frame. Empty NAHPU tables are left out of the
#    package, so a missing resource becomes an empty table.
def read_table(name: str) -> pd.DataFrame:
    if not package.has_resource(name):
        return pd.DataFrame()
    rows = package.get_resource(name).read_rows()
    return pd.DataFrame([row.to_dict() for row in rows])


specimens = read_table("specimen")
taxonomy = read_table("taxonomy")
attributes = read_table("mammalattribute")
personnel = read_table("personnel")
events = read_table("collevent")
sites = read_table("site")
geography = read_table("geography")
parts = read_table("specimenpart")
enums = read_table("sqlite-enum-mappings")

# 3. Keep mammals and join the related tables.
specimens = specimens[specimens["taxonGroup"].isin(["Mammals", "General Mammals", "Bats"])]
catalog = (
    specimens.merge(taxonomy, left_on="speciesID", right_on="id", how="left")
    .merge(attributes, left_on="uuid", right_on="specimenUuid", how="left")
    .merge(
        personnel[["uuid", "initial"]].rename(columns={"uuid": "catalogerID"}),
        on="catalogerID",
        how="left",
    )
    .merge(
        events[["id", "siteID"]].rename(columns={"id": "collEventID"}),
        on="collEventID",
        how="left",
    )
    .merge(
        sites[["id", "geographyId"]].rename(columns={"id": "siteID"}),
        on="siteID",
        how="left",
    )
    .merge(
        geography.rename(columns={"id": "geographyId"}),
        on="geographyId",
        how="left",
    )
)

# 4. Decode the stored sex code with the package's enum mappings.
sex = enums[(enums["table"] == "mammalAttribute") & (enums["column"] == "sex")]
sex_labels = dict(zip(sex["sqlite_index"], sex["display_name"]))
catalog["sex_label"] = catalog["sex"].map(sex_labels)

# 5. Collapse each specimen's parts into one cell, in part order.
part_list = (
    parts.sort_values("id")
    .groupby("specimenUuid")["type"]
    .agg("; ".join)
    .rename("parts")
)
catalog = catalog.merge(part_list, left_on="uuid", right_index=True, how="left")

# 6. Shape the output columns and write the CSV.
catalog = catalog.sort_values(["initial", "fieldNumber"])
species = catalog["genus"] + " " + catalog["specificEpithet"].fillna("sp.")
output = pd.DataFrame(
    {
        "field_id": catalog["initial"] + catalog["fieldNumber"].astype("Int64").astype("string"),
        "species": species,
        "sex": catalog["sex_label"],
        "country": catalog["country"],
        "locality": catalog["locality"],
        "collection_date": catalog["collectionDate"],
        "parts": catalog["parts"],
    }
)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
output.to_csv(OUTPUT, index=False)
print(f"Wrote {len(output)} specimens to {OUTPUT}")
