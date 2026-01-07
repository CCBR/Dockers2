#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
setRepositories(ind = 1:3)

remotes::install_cran(
  "gypsum",
  repos = "https://bioc.r-universe.dev/",
  upgrade = "never"
)
remotes::install_bioc("celldex", upgrade = "never")

remotes::install_github("satijalab/seurat-wrappers@73466e3", upgrade = "never")

# https://github.com/chris-mcginnis-ucsf/DoubletFinder/issues/244
remotes::install_github(
  "chris-mcginnis-ucsf/DoubletFinder@3b420df",
  upgrade = "never"
)

remotes::install_version(
  "Routliers",
  repos = "https://cran.rstudio.com/",
  version = "0.0.0.3",
  upgrade = "never"
)
remotes::install_cran(
  "BPCells",
  repos = "https://bnprks.r-universe.dev",
  upgrade = "never"
)

abort_packages_not_installed <- function(...) {
  pkgs <- c(...)
  package_status <- lapply(pkgs, rlang::is_installed) |> unlist()
  names(package_status) <- pkgs
  packages_not_installed <- Filter(isFALSE, package_status)
  if (length(packages_not_installed) > 0) {
    msg <- paste0(
      "The following package(s) are required but are not installed: ",
      paste0(names(packages_not_installed), collapse = ", ")
    )
    stop(msg)
  }
}

abort_packages_not_installed(
  'SeuratWrappers',
  'DoubletFinder',
  'Routliers',
  'BPCells',
  'gypsum',
  'celldex'
)
