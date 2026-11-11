# lsumz-mammal-specify-frictionless

Convert a [NAHPU](https://www.nahpu.app) Data Package (Frictionless format) into
the LSUMZ Mammalogy Specify WorkBench incoming-data sheet: one row per mammal
specimen, with every specimen part written as a numbered preparation
(`PrepType1`, `PrepType1Count`, `PrepType1Location`, `PrepType2`, …).

The same conversion is provided in Python and in R. Both read the package with
the [Frictionless](https://frictionlessdata.io) library for their language and
produce identical output.

## Layout

```text
data/
  country-continent.csv         country name -> continent, for the Continent column
  example/
    ambang-shrews.nahpu-dp.zip  sample NAHPU Data Package (5 shrews and rats)
    expected-specify.csv        the matching rows of the LSUMZ sheet
python/
  nahpu_to_specify.py           Python converter (frictionless)
  pyproject.toml, uv.lock
  tests/
R/
  nahpu_to_specify.R            R converter (frictionless, here, tidyverse)
  tests/
results/                        converted sheets are written here
```

## Export the data from NAHPU

1. In NAHPU, open the project menu and select `Bundle records`.
2. Set `Bundle format` to `NAHPU Data Package`. Either archive format works.
3. Create the bundle and copy the `.nahpu-dp.zip` or `.nahpu-dp.tar.gz` file
   into `data/`.

The converters accept the archive, its extracted folder, or the extracted
`datapackage.json`.

## Python

Requires Python 3.10 or newer. With [uv](https://docs.astral.sh/uv/):

```bash
cd python
uv sync
uv run python nahpu_to_specify.py ../data/my-project.nahpu-dp.zip
```

Without uv, install the one dependency and run the script directly:

```bash
pip install frictionless
python python/nahpu_to_specify.py data/my-project.nahpu-dp.zip
```

The sheet is written to `results/my-project-specify.csv`. Use `-o PATH` to
choose another file and `--all-taxa` to keep non-mammal specimens. Run the
tests with `uv run pytest` from `python/`.

## R

Install the packages once:

```r
install.packages(c(
  "frictionless", "here", "dplyr", "tidyr", "readr", "purrr", "stringr",
  "lubridate", "testthat"
))
```

Then run from the repository root:

```bash
Rscript R/nahpu_to_specify.R data/my-project.nahpu-dp.zip
```

The optional second argument sets the output path; `--all-taxa` keeps
non-mammal specimens. From an R session, `source(here::here("R",
"nahpu_to_specify.R"))` and call `nahpu_to_specify(input, output)`. Run the
tests with:

```bash
Rscript -e 'testthat::test_file("R/tests/test-nahpu_to_specify.R")'
```

Run without arguments, either converter turns the bundled example into
`results/ambang-shrews-specify.csv`.

## How the columns are filled

| Column                                             | Source in the NAHPU Data Package                                |
| -------------------------------------------------- | --------------------------------------------------------------- |
| Catalog Number                                     | `specimen.museumID`                                             |
| Class, Order, Family, Genus, Species               | `taxonomy` of `specimen.speciesID`                              |
| Sex                                                | `mammalAttribute.sex`, decoded with `mappings/sqlite_enums.csv` |
| Continent                                          | `geography.country` looked up in `data/country-continent.csv`   |
| Country, State, County                             | `geography` of the collecting event's site                      |
| Locality Name                                      | `geography.municipality` and `locality`, joined with `; `       |
| Elevation, Latitude, Longitude, MaxErrorDistance   | the specimen's coordinate, or the event site's only coordinate  |
| Elevation Unit                                     | `m` when an elevation is recorded                               |
| Collector1LastName                                 | cataloger's `personnel.name`, as `Last, First`                  |
| Field Number                                       | `specimen.fieldNumber` (project field number when unset)        |
| Start Date                                         | `specimen.collectionDate`, as `dd/mm/yyyy`                      |
| PrepType*n*, PrepType*n*Count, PrepType*n*Location | `specimenPart.type`, `count`, `storageLocation`, in part order  |
| Remarks                                            | `mammalAttribute.remark`                                        |
| OtherCollection OtherCollNumber                    | left blank                                                      |
| Total Length, TailLength, HFLength, Ear, Weight    | `mammalAttribute` measurements                                  |

Notes:

- Only specimens in the Mammals, General Mammals, or Bats taxon groups are kept,
  unless `--all-taxa` is given.
- The number of preparation groups follows the specimen with the most parts;
  shorter rows leave the extra columns blank. `Remarks` follows the second
  group, as on the LSUMZ sheet.
- Measurements are bracketed when the accuracy note says so, following NAHPU's
  bundled `LSUMZ-mammalogy` export preset (for example, `[150]` for a partially
  eaten specimen's total length).
- Collector names are flipped by moving the last word to the front. Check
  two-word family names before uploading.
- A country missing from `data/country-continent.csv` leaves `Continent` blank
  and prints a warning. Add the country to the file to fix it.
