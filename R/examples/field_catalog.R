# Tutorial 3 example: reshape a NAHPU Data Package into a field catalog.
#
# Each row is one specimen with its field ID, name, sex, place, date, and parts.
# Run from the repository root:
#
#   Rscript R/examples/field_catalog.R

library(dplyr)
library(frictionless)
library(here)
library(readr)
library(stringr)

here::i_am("R/examples/field_catalog.R")

archive <- here("data", "example", "ambang-shrews.nahpu-dp.zip")
extracted <- here("data", "extracted", "ambang-shrews")
output_path <- here("results", "ambang-shrews-field-catalog.csv")

# 1. Extract the archive and open the package.
utils::unzip(archive, exdir = extracted)
package <- read_package(file.path(extracted, "datapackage.json"))
print(resource_names(package))

# 2. Read a table into a tibble. Empty NAHPU tables are left out of the
#    package, so a missing resource becomes an empty table.
read_table <- function(name) {
  if (!name %in% resource_names(package)) {
    return(tibble())
  }
  read_resource(package, name)
}

specimens <- read_table("specimen")
taxonomy <- read_table("taxonomy")
attributes <- read_table("mammalattribute")
personnel <- read_table("personnel")
events <- read_table("collevent")
sites <- read_table("site")
geography <- read_table("geography")
parts <- read_table("specimenpart")
enums <- read_table("sqlite-enum-mappings")

# 3. Keep mammals and join the related tables.
catalog <- specimens |>
  filter(taxonGroup %in% c("Mammals", "General Mammals", "Bats")) |>
  left_join(taxonomy, by = c("speciesID" = "id")) |>
  left_join(attributes, by = c("uuid" = "specimenUuid")) |>
  left_join(select(personnel, uuid, initial), by = c("catalogerID" = "uuid")) |>
  left_join(select(events, id, siteID), by = c("collEventID" = "id")) |>
  left_join(select(sites, id, geographyId), by = c("siteID" = "id")) |>
  left_join(geography, by = c("geographyId" = "id"))

# 4. Decode the stored sex code with the package's enum mappings.
sex_labels <- enums |>
  filter(table == "mammalAttribute", column == "sex") |>
  transmute(sex = as.integer(sqlite_index), sex_label = display_name)
catalog <- left_join(catalog, sex_labels, by = "sex")

# 5. Collapse each specimen's parts into one cell, in part order.
part_list <- parts |>
  arrange(id) |>
  group_by(specimenUuid) |>
  summarise(parts = str_c(type, collapse = "; "))
catalog <- left_join(catalog, part_list, by = c("uuid" = "specimenUuid"))

# 6. Shape the output columns and write the CSV.
field_catalog <- catalog |>
  arrange(initial, fieldNumber) |>
  transmute(
    field_id = str_c(initial, fieldNumber),
    species = str_c(genus, " ", coalesce(specificEpithet, "sp.")),
    sex = sex_label,
    country,
    locality,
    collection_date = collectionDate,
    parts
  )
dir.create(dirname(output_path), showWarnings = FALSE, recursive = TRUE)
write_csv(field_catalog, output_path, na = "")
message("Wrote ", nrow(field_catalog), " specimens to ", output_path)
