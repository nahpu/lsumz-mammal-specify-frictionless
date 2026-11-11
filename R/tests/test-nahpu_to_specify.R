# Run with: Rscript -e 'testthat::test_file("R/tests/test-nahpu_to_specify.R")'
library(testthat)

source(here::here("R", "nahpu_to_specify.R"))

example <- here::here("data", "example")

read_lines_plain <- function(path) readr::read_lines(path)

test_that("the example matches the LSUMZ sheet", {
  output <- tempfile(fileext = ".csv")
  nahpu_to_specify(file.path(example, "ambang-shrews.nahpu-dp.zip"), output)

  expect_identical(
    read_lines_plain(output),
    read_lines_plain(file.path(example, "expected-specify.csv"))
  )
})

test_that("an extracted package converts the same way", {
  folder <- tempfile("package-")
  utils::unzip(file.path(example, "ambang-shrews.nahpu-dp.zip"), exdir = folder)
  output <- tempfile(fileext = ".csv")
  nahpu_to_specify(folder, output)

  expect_identical(
    read_lines_plain(output),
    read_lines_plain(file.path(example, "expected-specify.csv"))
  )
})

test_that("names, dates, and measurements are formatted for Specify", {
  expect_identical(last_name_first("Heru Handika"), "Handika, Heru")
  expect_identical(last_name_first("Mary Ann Smith"), "Smith, Mary Ann")
  expect_identical(last_name_first("Handika, Heru"), "Handika, Heru")
  expect_identical(format_date("2016-02-17"), "17/02/2016")
  expect_identical(format_number(c(148, 12.26, NA)), c("148", "12.26", ""))
  expect_identical(format_measurement(150, "Partially eaten", "totalLength"), "[150]")
  expect_identical(format_measurement(12.5, "Partially eaten", "weight"), "[12.5]")
  expect_identical(format_measurement(12.5, "Accurate", "weight"), "12.5")
})

test_that("remarks follow the second preparation group", {
  header <- sheet_columns(3)
  expect_identical(which(header == "Remarks"), which(header == "PrepType2Location") + 1L)
  expect_identical(sheet_columns(0)[18], "Remarks")
})
