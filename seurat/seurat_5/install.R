#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
setRepositories(ind = 1:3)
remotes::install_github("satijalab/seurat-wrappers", upgrade = "never")
remotes::install_github("chris-mcginnis-ucsf/DoubletFinder", upgrade = "never")
remotes::install_version("mdelacre/Routliers", version = "0.0.0.3", upgrade = "never")
remotes::install_cran("BPCells", repos = c("https://bnprks.r-universe.dev"), upgrade = "never")