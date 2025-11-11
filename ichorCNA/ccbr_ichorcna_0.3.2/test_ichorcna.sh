#!/bin/bash
set -e

echo "Testing ichorCNA v0.3.2 installation..."

# Create test directories
mkdir -p /data2/ichorcna_test/output

# Set ichorCNA path (should be set by Dockerfile, but fallback if needed)
if [ -z "${ICHORCNA_PATH}" ]; then
    ICHORCNA_PATH="/data2/ichorCNA"
fi

echo "Using ichorCNA at: ${ICHORCNA_PATH}"

# Test 1: Verify readCounter exists (from HMMcopy)
echo "Testing readCounter..."
readCounter --help > /dev/null 2>&1 || echo "Warning: readCounter not found (optional)"

# Test 2: Verify ichorCNA R package loads and check version
echo "Testing ichorCNA R package..."
Rscript -e "library(ichorCNA); v <- packageVersion('ichorCNA'); cat('ichorCNA version:', as.character(v), '\n'); stopifnot(as.character(v) == '0.3.2')"

# Test 3: Check required script exists
echo "Checking runIchorCNA.R script..."
if [ ! -f "${ICHORCNA_PATH}/scripts/runIchorCNA.R" ]; then
    echo "ERROR: runIchorCNA.R script not found"
    exit 1
fi

# Test 4: Check required extdata files exist (hg19 for test data)
echo "Checking extdata files..."
ls -lh ${ICHORCNA_PATH}/inst/extdata/gc_hg19_1000kb.wig
ls -lh ${ICHORCNA_PATH}/inst/extdata/map_hg19_1000kb.wig
ls -lh ${ICHORCNA_PATH}/inst/extdata/MBC_315.ctDNA.reads.wig

# Test 5: Run ichorCNA on test data (using hg19 references to match test data)
echo "Running ichorCNA on test sample..."
Rscript ${ICHORCNA_PATH}/scripts/runIchorCNA.R \
    --libdir "${ICHORCNA_PATH}" \
    --id test_sample \
    --WIG ${ICHORCNA_PATH}/inst/extdata/MBC_315.ctDNA.reads.wig \
    --gcWig ${ICHORCNA_PATH}/inst/extdata/gc_hg19_1000kb.wig \
    --mapWig ${ICHORCNA_PATH}/inst/extdata/map_hg19_1000kb.wig \
    --ploidy "c(2,3)" \
    --normal "c(0.5,0.6,0.7,0.8,0.9)" \
    --maxCN 5 \
    --includeHOMD False \
    --chrs "c(1:22, \"X\")" \
    --chrTrain "c(1:22)" \
    --estimateNormal True \
    --estimatePloidy True \
    --estimateScPrevalence False \
    --txnE 0.9999 \
    --txnStrength 10000 \
    --outDir /data2/ichorcna_test/output

# Test 6: Verify output files were created
echo "Verifying output files..."
if [ ! -f "/data2/ichorcna_test/output/test_sample.cna.seg" ]; then
    echo "ERROR: Expected output file test_sample.cna.seg not created"
    exit 1
fi

if [ ! -f "/data2/ichorcna_test/output/test_sample.seg.txt" ]; then
    echo "ERROR: Expected output file test_sample.seg.txt not created"
    exit 1
fi

# Test 7: Check output contains data
SEG_LINES=$(wc -l < /data2/ichorcna_test/output/test_sample.seg.txt)
if [ ${SEG_LINES} -lt 2 ]; then
    echo "ERROR: Output segmentation file is empty or too small"
    exit 1
fi

echo "✓ All ichorCNA v0.3.2 tests passed!"
echo ""
echo "Output files:"
ls -lh /data2/ichorcna_test/output/

# Clean up test directory
rm -rf /data2/ichorcna_test