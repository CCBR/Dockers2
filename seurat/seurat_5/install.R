#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
setRepositories(ind = 1:3)
remotes::install_github("satijalab/seurat-wrappers")
remotes::install_github("chris-mcginnis-ucsf/DoubletFinder")
remotes::install_github("mdelacre/Routliers")
remotes::install_cran("BPCells", repos = c("https://bnprks.r-universe.dev"))