# Renaming seqlevels on a TxDb *after* creation (renameSeqlevels /
# seqlevelsStyle<-) only patches the in-memory view -- AnnotationDbi::saveDb()
# does not persist it, so a freshly loadDb()'d copy still has the original
# NC_* names. Fix: rename seqlevels on the imported GRanges *before* building
# the TxDb, via txdbmaker::makeTxDbFromGRanges(), so the renamed names are
# baked into the TxDb's chrominfo table from the start.
gr <- rtracklayer::import("T2T-CHM13v2.0_genomic.gff", format = "gff3")

# RefSeq-Accn -> UCSC-style-name map for T2T-CHM13v2.0 (GCF_009914755.1), per
# NCBI's assembly report. chrM/NC_012920.1 (rCRS) isn't annotated in this GFF
# (only the 24 nuclear chromosomes are), so it's harmless to include here --
# it simply won't match any seqlevel in `gr` and will be dropped below.
map <- c(
    chr1 = "NC_060925.1", chr2 = "NC_060926.1", chr3 = "NC_060927.1",
    chr4 = "NC_060928.1", chr5 = "NC_060929.1", chr6 = "NC_060930.1",
    chr7 = "NC_060931.1", chr8 = "NC_060932.1", chr9 = "NC_060933.1",
    chr10 = "NC_060934.1", chr11 = "NC_060935.1", chr12 = "NC_060936.1",
    chr13 = "NC_060937.1", chr14 = "NC_060938.1", chr15 = "NC_060939.1",
    chr16 = "NC_060940.1", chr17 = "NC_060941.1", chr18 = "NC_060942.1",
    chr19 = "NC_060943.1", chr20 = "NC_060944.1", chr21 = "NC_060945.1",
    chr22 = "NC_060946.1", chrX = "NC_060947.1", chrY = "NC_060948.1",
    chrM = "NC_012920.1"
)
# renameSeqlevels() wants names = old (current) seqlevels, values = new names.
map <- setNames(names(map), map)
map <- map[names(map) %in% GenomeInfoDb::seqlevels(gr)]
gr <- GenomeInfoDb::renameSeqlevels(gr, map)

# Set seqlengths too (also must happen before makeTxDbFromGRanges(), for the
# same reason as the renaming above -- it doesn't persist via saveDb() if
# done on the TxDb after the fact). Chromosome lengths come from NCBI's
# assembly report (SequenceLength column, keyed by RefSeq-Accn).
report <- read.delim("assembly_report.txt", comment.char = "#", header = FALSE)
colnames(report) <- c(
    "SequenceName", "SequenceRole", "AssignedMolecule",
    "AssignedMoleculeLocationType", "GenBankAccn", "Relationship",
    "RefSeqAccn", "AssemblyUnit", "SequenceLength", "UCSCStyleName"
)
lengths_map <- setNames(report$SequenceLength, report$UCSCStyleName)
GenomeInfoDb::seqlengths(gr) <- lengths_map[GenomeInfoDb::seqlevels(gr)]

# ── chrR (synthetic rDNA-model contig used by ASPEN's hs1_chrR genome) ───────
# chrR.gtf is a small (25-feature) GTF describing the rDNA repeat unit
# (IGS/ETS/18S/ITS/5.8S/28S/TTF1 sites etc.) -- not part of NCBI's
# T2T-CHM13v2.0 annotation, since chrR is a synthetic contig ASPEN adds in
# place of the (masked) rDNA arrays. It's imported separately and merged into
# the same GRanges *before* TxDb construction, using the same import/rename
# approach as the main annotation, so a single combined TxDb covers both
# hs1 (no chrR) and hs1_chrR (with chrR) callers.
chrR_gr <- rtracklayer::import("chrR.gtf", format = "gtf")

# rtracklayer's GTF parser gives us gene_id/transcript_id/exon_number columns
# but no ID/Parent hierarchy (that's a GFF3-ism). The main `gr` above was
# parsed as GFF3 and relies on ID/Parent to link gene -> transcript -> exon,
# so we synthesize the same ID/Parent columns here from gene_id/transcript_id
# so the two GRanges merge into one consistent hierarchy.
is_gene <- chrR_gr$type == "gene"
is_tx <- chrR_gr$type == "transcript"
is_exon <- chrR_gr$type == "exon"

chrR_gr$ID <- NA_character_
chrR_gr$Parent <- NA_character_
chrR_gr$ID[is_gene] <- paste0("gene-", chrR_gr$gene_id[is_gene])
chrR_gr$ID[is_tx] <- paste0("rna-", chrR_gr$transcript_id[is_tx])
chrR_gr$Parent[is_tx] <- paste0("gene-", chrR_gr$gene_id[is_tx])
chrR_gr$ID[is_exon] <- paste0(
    "exon-", chrR_gr$transcript_id[is_exon], "-", chrR_gr$exon_number[is_exon]
)
chrR_gr$Parent[is_exon] <- paste0("rna-", chrR_gr$transcript_id[is_exon])

GenomeInfoDb::seqlengths(chrR_gr) <- c(chrR = 44838L)

combined_gr <- c(gr, chrR_gr)

txdb <- txdbmaker::makeTxDbFromGRanges(combined_gr, taxonomyId = 9606)

AnnotationDbi::saveDb(txdb, file = "TxDb.Hsapiens.NCBI.T2T.CHM13v2.0.sqlite")
cat("DONE\n")
