#!/usr/bin/env Rscript
cat("Testing superFreq installation...\n")
library(superFreq)
cat("superFreq loaded successfully!\n")
cat("Version:", as.character(packageVersion("superFreq")), "\n")
q(status=0)