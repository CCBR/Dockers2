#!/usr/bin/env python3
import argparse
import csv

HLA_CLASS_I_REGIONS = {
    "HLA-A": ("chr6", 29942500, 29947000),
    "HLA-C": ("chr6", 31266749, 31274092),
    "HLA-B": ("chr6", 31351875, 31359179),
}

FIELDNAMES = [
    "tumor_sample",
    "normal_sample",
    "locus",
    "bam",
    "chrom",
    "pos1",
    "ref",
    "base",
    "allele1",
    "allele2",
]


def class_i_locus_for_variant(chrom, pos):
    for locus, (region_chrom, start, end) in HLA_CLASS_I_REGIONS.items():
        if chrom == region_chrom and start <= pos <= end:
            return locus
    return None


def parse_hla_consensus(path):
    rows_by_locus = {}
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="	")
        for row in reader:
            locus = row["locus"].strip()
            if locus not in HLA_CLASS_I_REGIONS:
                continue
            if locus in rows_by_locus:
                raise ValueError(f"Duplicate consensus row for {locus}")

            allele1 = row["consensus_allele1"].strip()
            allele2 = row["consensus_allele2"].strip()
            if not allele1 or not allele2:
                raise ValueError(f"Missing complete consensus call for {locus}")

            rows_by_locus[locus] = row

    missing = [locus for locus in HLA_CLASS_I_REGIONS if locus not in rows_by_locus]
    if missing:
        raise ValueError(f"Missing complete consensus calls for: {', '.join(missing)}")

    return [rows_by_locus[locus] for locus in HLA_CLASS_I_REGIONS]


def _is_biallelic_snv(ref, alt):
    return "," not in alt and len(ref) == 1 and len(alt) == 1


def _validate_consensus_rows(consensus_rows):
    rows_by_locus = {}
    for row in consensus_rows:
        locus = (row.get("locus") or "").strip()
        if locus not in HLA_CLASS_I_REGIONS:
            raise ValueError("Consensus rows must contain HLA-A, HLA-B, and HLA-C")
        if locus in rows_by_locus:
            raise ValueError(f"Duplicate consensus row for {locus}")

        allele1 = (row.get("consensus_allele1") or "").strip()
        allele2 = (row.get("consensus_allele2") or "").strip()
        if not allele1 or not allele2:
            raise ValueError(f"Missing complete consensus call for {locus}")

        rows_by_locus[locus] = row

    missing = [locus for locus in HLA_CLASS_I_REGIONS if locus not in rows_by_locus]
    if missing:
        raise ValueError(f"Missing complete consensus calls for: {', '.join(missing)}")

    return rows_by_locus


def build_clover_rows(consensus_rows, tumor_sample, normal_sample, tumor_bam, vcf_path):
    consensus_by_locus = _validate_consensus_rows(consensus_rows)
    rows = []

    with open(vcf_path, newline="", encoding="utf-8") as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue

            chrom, pos, _vid, ref, alt, *_rest = line.rstrip("\n").split("\t")
            locus = class_i_locus_for_variant(chrom, int(pos))
            if locus is None or locus not in consensus_by_locus:
                continue
            if not _is_biallelic_snv(ref, alt):
                continue

            consensus = consensus_by_locus[locus]
            rows.append(
                {
                    "tumor_sample": tumor_sample,
                    "normal_sample": normal_sample,
                    "locus": locus,
                    "bam": tumor_bam,
                    "chrom": chrom,
                    "pos1": pos,
                    "ref": ref,
                    "base": alt,
                    "allele1": consensus["consensus_allele1"].strip(),
                    "allele2": consensus["consensus_allele2"].strip(),
                }
            )

    return rows


def write_clover_config(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="	", fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Prepare CLOVER input rows from HLA consensus and somatic VCF files."
    )
    parser.add_argument("--tumor-sample", required=True)
    parser.add_argument("--normal-sample", required=True)
    parser.add_argument("--tumor-bam", required=True)
    parser.add_argument("--somatic-vcf", required=True)
    parser.add_argument("--hla-consensus", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    consensus_rows = parse_hla_consensus(args.hla_consensus)
    rows = build_clover_rows(
        consensus_rows=consensus_rows,
        tumor_sample=args.tumor_sample,
        normal_sample=args.normal_sample,
        tumor_bam=args.tumor_bam,
        vcf_path=args.somatic_vcf,
    )
    write_clover_config(rows, args.output)


if __name__ == "__main__":
    main()
