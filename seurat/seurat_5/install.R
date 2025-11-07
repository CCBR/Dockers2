#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
setRepositories(ind = 1:3)
remotes::install_github("satijalab/seurat-wrappers", upgrade = "never")

# https://github.com/chris-mcginnis-ucsf/DoubletFinder/issues/244
remotes::install_github("chris-mcginnis-ucsf/DoubletFinder@3b420df", upgrade = "never")

remotes::install_version("Routliers", repos = "https://cran.rstudio.com/", version = "0.0.0.3", upgrade = "never")
remotes::install_cran("BPCells", repos = "https://bnprks.r-universe.dev", upgrade = "never")
remotes::install_cran("gypsum", repos = "https://bioc.r-universe.dev/", upgrade = "never")