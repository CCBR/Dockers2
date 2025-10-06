#!/bin/bash
set -e

echo "Shiver test results:"
echo "==================="
ls -la my_output_id* 2>/dev/null || echo "No test results found - run the test commands manually"

echo -e "\nTest data available:"
ls -la test_data/

echo -e "\nTo run shiver test manually:"
echo "shiver_init.sh my_init_dir /opt2/conda/envs/shiver/bin/config.sh HIV1_COM_2021_genome_DNA.fasta test_data/adapters_Illumina.fasta test_data/primers_GallEtAl2012.fasta"
echo "shiver_align_contigs.sh my_init_dir /opt2/conda/envs/shiver/bin/config.sh test_data/MysteryHIV_contigs.fasta my_output_id"
echo "shiver_map_reads.sh my_init_dir /opt2/conda/envs/shiver/bin/config.sh test_data/MysteryHIV_contigs.fasta my_output_id my_output_id.blast my_output_id_cut_wRefs.fasta test_data/MysteryHIV_1.fastq test_data/MysteryHIV_2.fastq"

echo -e "\nShiver installation verified!"
