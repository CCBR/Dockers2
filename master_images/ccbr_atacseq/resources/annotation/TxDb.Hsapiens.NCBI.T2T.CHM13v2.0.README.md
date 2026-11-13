# `TxDb.Hsapiens.NCBI.T2T.CHM13v2.0.sqlite.gz`

A pre-built [`GenomicFeatures`](https://bioconductor.org/packages/GenomicFeatures/)
`TxDb` SQLite database for the T2T-CHM13v2.0 human genome assembly, shipped
inside the `nciccbr/ccbr_atacseq` image so ASPEN's R annotation scripts
(`ccbr_annotate_bed.R`, `ccbr_annotate_peaks.R`) can load it directly instead
of building it at container-build time or run time.

Built for [CCBR/Dockers2#422](https://github.com/CCBR/Dockers2/issues/422) /
[CCBR/ASPEN#123](https://github.com/CCBR/ASPEN/issues/123), to support the
`hs1` and `hs1_chrR` genomes in ASPEN.

## Why this exists (background)

The originally-requested `BiocT2T` package
(`BiocT2T::install_early_t2t_txdb()` → `TxDb.Hsapiens.NCBI.CHM13v2`) **does
not exist** — `https://github.com/bioc/BiocT2T` is a 404, and the package is
absent from the full Bioconductor 3.23 package list. There is also no
ready-made `TxDb.Hsapiens.NCBI.CHM13v2` package on Bioconductor. Instead,
this TxDb is built directly from NCBI's official T2T-CHM13v2.0 RefSeq
annotation.

## Source data

| Input | Source | Notes |
|---|---|---|
| `T2T-CHM13v2.0_genomic.gff.gz` | NCBI RefSeq assembly [`GCF_009914755.1`](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/009/914/755/GCF_009914755.1_T2T-CHM13v2.0/GCF_009914755.1_T2T-CHM13v2.0_genomic.gff.gz) | ~1.7GB uncompressed GFF3; only the 24 nuclear chromosomes are annotated (no mitochondrial/`chrM` features — `NC_012920.1` does not appear anywhere in this file). Not committed to the repo (too large); re-download when regenerating. |
| `assembly_report.txt` | Same NCBI directory, `..._assembly_report.txt` | Used only for the `SequenceLength` column (seqlengths), keyed by `UCSCStyleName`. Committed here (small, plain text). |
| `chrR.gtf` | Converted from the BED annotation in [vikramparalkar/rDNA-Mapping-Genomes](https://github.com/vikramparalkar/rDNA-Mapping-Genomes/blob/main/Human_hs1-rDNA_genome_v1.0_annotation.tar.gz) (`Human_hs1-rDNA_genome_v1.0_annotation.tar.gz`) | 25 features (`gene`/`transcript`/`exon`, one exon per transcript) describing the synthetic `chrR` contig that ASPEN's `hs1_chrR` genome build substitutes for the (masked) rDNA arrays: `IGS`, `Spacer_Promoter`, `Tsp_TTF1_site`, `Enhancer_Repeats`, `T0`–`T11_TTF1_site`, `47S_Promoter`, `5'_ETS`, `18S`, `ITS1`, `5.8S`, `ITS2`, `28S`, `3'_ETS`. The upstream file is BED format (`chrR.bed`); converted to GTF (`chrR.gtf`) so `rtracklayer::import()` yields a feature-typed (`gene`/`transcript`/`exon`) `GRanges` that `txdbmaker` can consume. Committed here. |

## Build steps (`build_txdb.R`)

Run with R ≥ 4.4 (built with R 4.4.3; `txdbmaker` 1.2.1, `rtracklayer` 1.66.0,
`GenomicFeatures` 1.58.0, `GenomeInfoDb` 1.42.3, `AnnotationDbi` 1.68.0,
`RSQLite` 2.3.9, `ChIPseeker` 1.42.1 used for verification):

1. **Import the main GFF3** via `rtracklayer::import(..., format = "gff3")`
   into a `GRanges`.
2. **Rename seqlevels to UCSC style** (`chr1`...`chr22`, `chrX`, `chrY`)
   using a hardcoded RefSeq-accession → UCSC-name map (`NC_060925.1` →
   `chr1`, ..., `NC_060948.1` → `chrY`), via
   `GenomeInfoDb::renameSeqlevels()`. `chrM`/`NC_012920.1` is included in
   the map for completeness but has no matching seqlevel in this GFF3, so
   it's silently dropped.
3. **Set seqlengths** on the same `GRanges` from `assembly_report.txt`'s
   `SequenceLength` column (keyed by `UCSCStyleName`), via
   `GenomeInfoDb::seqlengths()<-`.
4. **Merge in the `chrR` annotation**: import `chrR.gtf` via
   `rtracklayer::import(..., format = "gtf")`. Since it has no GFF3-style
   `ID`/`Parent` hierarchy (GTF uses flat `gene_id`/`transcript_id`
   attributes instead), synthesize matching `ID`/`Parent` columns
   (`gene-<gene_id>`, `rna-<transcript_id>`, `exon-<transcript_id>-<n>`) so
   it merges cleanly with the main `GRanges`'s hierarchy. Set
   `chrR`'s seqlength to 44838 (its full contig length). Combine both
   `GRanges` objects with `c()`.
5. **Build the TxDb** from the single combined `GRanges` via
   `txdbmaker::makeTxDbFromGRanges(combined_gr, taxonomyId = 9606)`.
6. **Save** via `AnnotationDbi::saveDb(txdb, file = "TxDb.Hsapiens.NCBI.T2T.CHM13v2.0.sqlite")`.
7. **Compress**: `gzip -9` the resulting `.sqlite` (~283MB → ~80MB) so it
   stays under GitHub's 100MB per-file push limit, and commit the `.gz`
   instead of the raw file.

To reproduce: download the GFF3 into this directory, decompress it, then
run `Rscript build_txdb.R` from this directory.

## ⚠️ Critical gotcha: rename/set-lengths *before* building the TxDb

Renaming seqlevels or setting seqlengths on a `TxDb` object **after** it's
already been constructed (e.g. `GenomeInfoDb::seqlevelsStyle(txdb) <-
"UCSC"`, or `renameSeqlevels(txdb, map)`, or `seqlengths(txdb) <- ...`)
only patches the in-memory R-level view. `AnnotationDbi::saveDb()` does
**not** persist that change — a freshly `loadDb()`'d copy of the saved file
still shows the original names/`NA` lengths. This is also why
`seqlevelsStyle(txdb) <- "UCSC"` isn't a viable fix here in the first place:
T2T-CHM13v2.0's RefSeq accessions aren't covered by `GenomeInfoDbData`'s
built-in rename tables, so it errors with *"found no sequence renaming map
compatible with seqname style 'UCSC'"* even before the persistence problem
would come up.

**The fix**: do all renaming and seqlength-setting on the source `GRanges`
*before* calling `txdbmaker::makeTxDbFromGRanges()` (not
`makeTxDbFromGFF()`, which re-imports the file internally and doesn't give
you a hook to pre-process it) — see steps 2–4 above.

## Loading it at runtime

No further seqlevel/style conversion is needed — the seqnames are already
UCSC-style (`chr1`...`chr22`, `chrX`, `chrY`, `chrR`), matching ASPEN's
`hs1`/`hs1_chrR` index naming:

```r
tdb <- AnnotationDbi::loadDb("/opt2/annotation/TxDb.Hsapiens.NCBI.T2T.CHM13v2.0.sqlite")
adb <- "org.Hs.eg.db"
```

## Contents / verification

| Check | Result |
|---|---|
| `seqlevels(txdb)` | `chr1`...`chr22`, `chrX`, `chrY`, `chrR` (25 total) |
| `seqlengths(txdb)` | populated for all 25 (e.g. `chr1` = 248387328, `chrR` = 44838); none `NA` |
| `transcripts(txdb)` | 189,061 (189,036 from the main GFF3 + 25 from `chrR.gtf`) |
| `exons(txdb)` | 2,147,917 (+ 25 chrR exons) |
| `cds(txdb)` | 1,678,245 |
| `genes(txdb)` | 47,916 (+ 25 chrR "genes") |
| `ChIPseeker::annotatePeak()` | Verified on dummy peaks on `chr1`, `chr19`, `chrX`, and `chrR` (e.g. a peak at `chrR:13000-13499` correctly annotates as `Promoter (<=1kb)` near the `18S` rDNA gene) |

`chrM` is not present as a seqlevel (absent from NCBI's T2T-CHM13v2.0 GFF3
entirely). Peaks on `chrM`, if ever called, will simply get no
gene/transcript overlap from `annotatePeak()` — same as any other
unannotated contig.

## Used by

- `master_images/ccbr_atacseq/Dockerfile.v13` (Layer 4/5) — copies and
  gunzips this file to `/opt2/annotation/TxDb.Hsapiens.NCBI.T2T.CHM13v2.0.sqlite`
  in the image.
- ASPEN's `ccbr_annotate_bed.R` / `ccbr_annotate_peaks.R` — dispatch both
  `hs1` and `hs1_chrR` genomes to this same TxDb (see
  [CCBR/ASPEN#123](https://github.com/CCBR/ASPEN/issues/123)).
