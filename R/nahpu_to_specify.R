# Convert a NAHPU Data Package into an LSUMZ Mammalogy Specify WorkBench sheet.
#
# The input is a NAHPU Data Package (Frictionless) exported from NAHPU's
# `Bundle records`: the `.zip` or `.tar.gz` archive, its extracted folder, or
# its `datapackage.json`. The output is a CSV with one row per mammal specimen,
# in the column layout of the LSUMZ Mammalogy incoming-data sheet.
#
# Usage:
#   Rscript R/nahpu_to_specify.R [INPUT] [OUTPUT] [--all-taxa]

suppressPackageStartupMessages({
  library(dplyr)
  library(frictionless)
  library(here)
  library(lubridate)
  library(purrr)
  library(readr)
  library(stringr)
  library(tidyr)
})

here::i_am("R/nahpu_to_specify.R")

mammal_groups <- c("Mammals", "General Mammals", "Bats")

leading_columns <- c(
  "Catalog Number", "Class", "Order", "Family", "Genus", "Species", "Sex",
  "Continent", "Country", "State", "County", "Locality Name", "Elevation",
  "Elevation Unit", "Collector1LastName", "Field Number", "Start Date"
)
trailing_columns <- c(
  "Latitude", "Longitude", "MaxErrorDistance", "OtherCollection OtherCollNumber",
  "Total Length", "TailLength", "HFLength", "Ear", "Weight"
)
# Remarks sits after the second preparation group, as on the LSUMZ sheet.
remarks_after_group <- 2

# Measurements written in brackets when the accuracy note matches, as in
# NAHPU's bundled LSUMZ-mammalogy export preset.
bracket_rules <- list(
  totalLength = c("Tail cropped", "Other reason", "Partially eaten"),
  tailLength = c("Tail cropped", "Partially eaten", "Other reason"),
  earLength = c("Ear damaged", "Other reason"),
  hindFootLength = c("hindFootLength", "Partially eaten")
)

#' Reads the Frictionless package at `path`, extracting archives first.
open_package <- function(path) {
  if (dir.exists(path)) {
    return(read_package(file.path(path, "datapackage.json")))
  }
  if (basename(path) == "datapackage.json") {
    return(read_package(path))
  }
  folder <- tempfile("nahpu-dp-")
  dir.create(folder)
  if (str_detect(path, "\\.zip$")) {
    utils::unzip(path, exdir = folder)
  } else if (str_detect(path, "\\.(tar\\.gz|tgz)$")) {
    utils::untar(path, exdir = folder)
  } else {
    stop("Not a NAHPU Data Package: ", path)
  }
  read_package(file.path(folder, "datapackage.json"))
}

#' Reads resource `name`; empty NAHPU tables are left out of the package.
read_table <- function(package, name, empty) {
  if (!name %in% resource_names(package)) {
    return(empty)
  }
  suppressMessages(read_resource(package, name))
}

#' `Heru Handika` -> `Handika, Heru`; names with a comma are kept.
last_name_first <- function(name) {
  str_replace(name, "^([^,]*[^\\s,])\\s+([^\\s,]+)$", "\\2, \\1")
}

#' ISO `2016-02-17` -> `17/02/2016`; anything else is kept as text.
format_date <- function(value) {
  parsed <- suppressWarnings(ymd(str_sub(value, 1, 10), quiet = TRUE))
  if_else(is.na(parsed), coalesce(as.character(value), ""), format(parsed, "%d/%m/%Y"))
}

#' Writes numbers without a trailing `.0`, as NAHPU's exports do.
format_number <- function(value) {
  text <- if (is.numeric(value)) {
    format(value, scientific = FALSE, trim = TRUE, digits = 15, drop0trailing = TRUE)
  } else {
    as.character(value)
  }
  text <- str_remove(text, "\\.0$")
  coalesce(if_else(is.na(value), NA_character_, text), "")
}

format_measurement <- function(value, accuracy, field) {
  text <- format_number(value)
  accuracy <- coalesce(accuracy, "")
  bracket <- if (field == "weight") {
    accuracy != "" & accuracy != "Accurate"
  } else {
    map_lgl(accuracy, \(note) any(str_detect(note, fixed(bracket_rules[[field]]))))
  }
  if_else(text != "" & bracket, str_c("[", text, "]"), text)
}

#' The sheet's header for `group_count` preparation groups.
sheet_columns <- function(group_count) {
  groups <- map(seq_len(group_count), \(index) {
    group <- str_c("PrepType", index, c("", "Count", "Location"))
    if (index == remarks_after_group) c(group, "Remarks") else group
  })
  middle <- unlist(groups)
  if (group_count < remarks_after_group) middle <- c(middle, "Remarks")
  c(leading_columns, middle, trailing_columns)
}

#' Builds one LSUMZ sheet row per specimen in `package`.
convert <- function(package, all_taxa = FALSE) {
  specimens <- read_table(package, "specimen", tibble(uuid = character()))
  if (!all_taxa) {
    specimens <- filter(specimens, taxonGroup %in% mammal_groups)
  }
  taxonomy <- read_table(package, "taxonomy", tibble(id = integer()))
  attributes <- read_table(package, "mammalattribute", tibble(specimenUuid = character()))
  personnel <- read_table(package, "personnel", tibble(uuid = character()))
  events <- read_table(package, "collevent", tibble(id = integer(), siteID = integer()))
  sites <- read_table(package, "site", tibble(id = integer(), geographyId = integer()))
  geography <- read_table(package, "geography", tibble(id = integer()))
  coordinates <- read_table(package, "coordinate", tibble(id = integer(), siteID = integer()))
  parts <- read_table(package, "specimenpart", tibble(id = integer(), specimenUuid = character()))
  sex_labels <- read_table(package, "sqlite-enum-mappings", tibble(table = character())) |>
    filter(table == "mammalAttribute", column == "sex") |>
    transmute(sex = as.integer(sqlite_index), sex_label = display_name)
  continents <- read_csv(here("data", "country-continent.csv"), show_col_types = FALSE) |>
    transmute(country_key = str_to_lower(country), continent)

  # NAHPU uses the specimen's coordinate, or else the event site's only one.
  site_coordinates <- coordinates |>
    group_by(siteID) |>
    filter(n() == 1) |>
    ungroup() |>
    select(siteID, site_coordinate = id)

  base <- specimens |>
    left_join(taxonomy, by = c("speciesID" = "id")) |>
    left_join(attributes, by = c("uuid" = "specimenUuid")) |>
    left_join(sex_labels, by = "sex") |>
    left_join(select(personnel, uuid, collector = name), by = c("catalogerID" = "uuid")) |>
    left_join(select(events, id, event_site = siteID), by = c("collEventID" = "id")) |>
    left_join(select(sites, id, geographyId), by = c("event_site" = "id")) |>
    left_join(geography, by = c("geographyId" = "id")) |>
    left_join(site_coordinates, by = c("event_site" = "siteID")) |>
    mutate(coordinate_id = coalesce(coordinateID, site_coordinate)) |>
    left_join(coordinates, by = c("coordinate_id" = "id"), suffix = c("", ".coordinate")) |>
    mutate(field_number = coalesce(fieldNumber, projectFieldNumber)) |>
    arrange(coalesce(catalogerID, ""), is.na(field_number), field_number, uuid)

  missing <- base |>
    mutate(country_key = str_to_lower(country)) |>
    anti_join(continents, by = "country_key") |>
    filter(!is.na(country)) |>
    distinct(country)
  walk(missing$country, \(name) warning("No continent for country '", name, "'.", call. = FALSE))

  sheet <- base |>
    mutate(country_key = str_to_lower(country)) |>
    left_join(continents, by = "country_key") |>
    transmute(
      uuid,
      `Catalog Number` = coalesce(museumID, ""),
      Class = coalesce(taxonClass, ""),
      Order = coalesce(taxonOrder, ""),
      Family = coalesce(taxonFamily, ""),
      Genus = coalesce(genus, ""),
      Species = coalesce(specificEpithet, ""),
      Sex = coalesce(sex_label, format_number(sex)),
      Continent = coalesce(continent, ""),
      Country = coalesce(country, ""),
      State = coalesce(stateProvince, ""),
      County = coalesce(county, ""),
      `Locality Name` = pmap_chr(
        list(municipality, locality),
        \(...) str_c(discard(c(...), \(x) is.na(x) || x == ""), collapse = "; ")
      ),
      Elevation = format_number(elevationInMeter),
      `Elevation Unit` = if_else(Elevation != "", "m", ""),
      Collector1LastName = last_name_first(coalesce(collector, "")),
      `Field Number` = format_number(field_number),
      `Start Date` = format_date(collectionDate),
      Remarks = coalesce(remark, ""),
      Latitude = format_number(decimalLatitude),
      Longitude = format_number(decimalLongitude),
      MaxErrorDistance = format_number(uncertaintyInMeters),
      `OtherCollection OtherCollNumber` = "",
      `Total Length` = format_measurement(totalLength, accuracy, "totalLength"),
      TailLength = format_measurement(tailLength, accuracy, "tailLength"),
      HFLength = format_measurement(hindFootLength, accuracy, "hindFootLength"),
      Ear = format_measurement(earLength, accuracy, "earLength"),
      Weight = format_measurement(weight, accuracy, "weight")
    )

  preparations <- parts |>
    semi_join(sheet, by = c("specimenUuid" = "uuid")) |>
    arrange(id) |>
    group_by(specimenUuid) |>
    mutate(index = row_number()) |>
    ungroup() |>
    transmute(
      uuid = specimenUuid,
      index,
      PrepType = coalesce(as.character(type), ""),
      PrepTypeCount = coalesce(as.character(count), ""),
      PrepTypeLocation = coalesce(as.character(storageLocation), "")
    ) |>
    pivot_longer(starts_with("PrepType"), names_to = "field", values_to = "value") |>
    mutate(column = str_replace(field, "^PrepType", str_c("PrepType", index))) |>
    select(uuid, column, value) |>
    pivot_wider(names_from = column, values_from = value)

  group_count <- preparations |>
    select(starts_with("PrepType")) |>
    names() |>
    str_extract("\\d+") |>
    as.integer() |>
    c(0L) |>
    max()
  header <- sheet_columns(group_count)
  sheet |>
    left_join(preparations, by = "uuid") |>
    mutate(across(everything(), \(x) coalesce(as.character(x), ""))) |>
    (\(data) {
      for (column in setdiff(header, names(data))) data[[column]] <- ""
      data
    })() |>
    select(all_of(header))
}

#' Converts `input` and writes the sheet to `output`.
nahpu_to_specify <- function(input, output, all_taxa = FALSE) {
  sheet <- convert(open_package(input), all_taxa = all_taxa)
  dir.create(dirname(output), showWarnings = FALSE, recursive = TRUE)
  write_csv(sheet, output, na = "")
  message("Wrote ", nrow(sheet), " specimens to ", output)
  invisible(sheet)
}

output_stem <- function(input) {
  name <- basename(input)
  if (name == "datapackage.json") name <- basename(dirname(input))
  name |>
    str_remove("\\.(tar\\.gz|tgz|zip)$") |>
    str_remove("\\.nahpu-dp$")
}

if (sys.nframe() == 0) {
  args <- commandArgs(trailingOnly = TRUE)
  all_taxa <- "--all-taxa" %in% args
  args <- setdiff(args, "--all-taxa")
  input <- if (length(args) >= 1) {
    args[[1]]
  } else {
    here("data", "example", "ambang-shrews.nahpu-dp.zip")
  }
  output <- if (length(args) >= 2) {
    args[[2]]
  } else {
    here("results", str_c(output_stem(input), "-specify.csv"))
  }
  nahpu_to_specify(input, output, all_taxa = all_taxa)
}
