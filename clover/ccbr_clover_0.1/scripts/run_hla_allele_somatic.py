#!/usr/bin/env python3
import argparse
import csv
import os
import re
import subprocess
from typing import Dict, List, Optional

SUMMARY_FIELDNAMES = [
    "tumor_sample",
    "normal_sample",
    "locus",
    "chrom",
    "pos1",
    "ref",
    "alt",
    "allele1",
    "allele2",
    "matching_allele",
    "allele1_identity_num",
    "allele1_identity_den",
    "allele1_identity_pct",
    "allele1_score",
    "allele1_evalue",
    "allele2_identity_num",
    "allele2_identity_den",
    "allele2_identity_pct",
    "allele2_score",
    "allele2_evalue",
    "status",
    "run_dir",
    "comparison_report",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_SCRIPT = os.environ.get(
    "CLOVER_EXTRACTOR",
    os.path.join(SCRIPT_DIR, "extract_reads_paired.py"),
)
BLAST_DB = os.environ.get(
    "CLOVER_BLAST_DB",
    "/data/CCBR_Pipeliner/Pipelines/LIBERTY/CLOVER/blastdb/hla_gen_db",
)


def safe_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text).strip())


def load_config_rows(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = []
        for row in reader:
            cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            rows.append(cleaned)
        return rows


def parse_blast_metrics(path: str) -> Optional[Dict[str, str]]:
    if not os.path.exists(path):
        return None

    best = None
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 5:
                continue

            nident = fields[0]
            align_len = fields[1]
            pident = fields[2]
            bitscore = fields[3]
            evalue = fields[4]

            try:
                pident_f = float(pident)
                bitscore_f = float(bitscore)
            except ValueError:
                continue

            current = {
                "identity_num": nident,
                "identity_den": align_len,
                "identity_pct": pident,
                "score": bitscore,
                "evalue": evalue,
                "_identity_pct_float": pident_f,
                "_score_float": bitscore_f,
            }

            if best is None:
                best = current
                continue

            if current["_identity_pct_float"] > best["_identity_pct_float"]:
                best = current
            elif current["_identity_pct_float"] == best["_identity_pct_float"] and current["_score_float"] > best["_score_float"]:
                best = current

    if best is None:
        return None

    best.pop("_identity_pct_float", None)
    best.pop("_score_float", None)
    return best


def choose_matching_allele(
    allele1: str,
    metrics1: Optional[Dict[str, str]],
    allele2: str,
    metrics2: Optional[Dict[str, str]],
) -> str:
    if metrics1 is None and metrics2 is None:
        return "tie"
    if metrics1 is None:
        return allele2
    if metrics2 is None:
        return allele1

    p1 = float(metrics1["identity_pct"])
    p2 = float(metrics2["identity_pct"])

    if p1 > p2:
        return allele1
    if p2 > p1:
        return allele2

    s1 = float(metrics1["score"])
    s2 = float(metrics2["score"])
    if s1 > s2:
        return allele1
    if s2 > s1:
        return allele2

    return "tie"


def build_summary_row(
    cfg_row: Dict[str, str],
    metrics1: Optional[Dict[str, str]],
    metrics2: Optional[Dict[str, str]],
    matching_allele: str,
    status: str,
    run_dir: str,
    comparison_report: str,
) -> Dict[str, str]:
    return {
        "tumor_sample": cfg_row.get("tumor_sample", ""),
        "normal_sample": cfg_row.get("normal_sample", ""),
        "locus": cfg_row.get("locus", ""),
        "chrom": cfg_row.get("chrom", ""),
        "pos1": cfg_row.get("pos1", ""),
        "ref": cfg_row.get("ref", ""),
        "alt": cfg_row.get("base", ""),
        "allele1": cfg_row.get("allele1", ""),
        "allele2": cfg_row.get("allele2", ""),
        "matching_allele": matching_allele,
        "allele1_identity_num": (metrics1 or {}).get("identity_num", ""),
        "allele1_identity_den": (metrics1 or {}).get("identity_den", ""),
        "allele1_identity_pct": (metrics1 or {}).get("identity_pct", ""),
        "allele1_score": (metrics1 or {}).get("score", ""),
        "allele1_evalue": (metrics1 or {}).get("evalue", ""),
        "allele2_identity_num": (metrics2 or {}).get("identity_num", ""),
        "allele2_identity_den": (metrics2 or {}).get("identity_den", ""),
        "allele2_identity_pct": (metrics2 or {}).get("identity_pct", ""),
        "allele2_score": (metrics2 or {}).get("score", ""),
        "allele2_evalue": (metrics2 or {}).get("evalue", ""),
        "status": status,
        "run_dir": run_dir,
        "comparison_report": comparison_report,
    }


def write_summary(rows: List[Dict[str, str]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=SUMMARY_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_comparison_report(
    report_path: str,
    cfg_row: Dict[str, str],
    metrics1: Optional[Dict[str, str]],
    metrics2: Optional[Dict[str, str]],
    matching_allele: str,
    status: str,
    error_text: str = "",
) -> None:
    lines = [
        f"tumor_sample\t{cfg_row.get('tumor_sample', '')}",
        f"normal_sample\t{cfg_row.get('normal_sample', '')}",
        f"locus\t{cfg_row.get('locus', '')}",
        f"variant\t{cfg_row.get('chrom', '')}:{cfg_row.get('pos1', '')} {cfg_row.get('ref', '')}>{cfg_row.get('base', '')}",
        f"allele1\t{cfg_row.get('allele1', '')}",
        f"allele2\t{cfg_row.get('allele2', '')}",
        f"status\t{status}",
        f"matching_allele\t{matching_allele}",
        "",
        "allele\tidentity_num\tidentity_den\tidentity_pct\tscore\tevalue",
        "{0}\t{1}\t{2}\t{3}\t{4}\t{5}".format(
            cfg_row.get("allele1", ""),
            (metrics1 or {}).get("identity_num", ""),
            (metrics1 or {}).get("identity_den", ""),
            (metrics1 or {}).get("identity_pct", ""),
            (metrics1 or {}).get("score", ""),
            (metrics1 or {}).get("evalue", ""),
        ),
        "{0}\t{1}\t{2}\t{3}\t{4}\t{5}".format(
            cfg_row.get("allele2", ""),
            (metrics2 or {}).get("identity_num", ""),
            (metrics2 or {}).get("identity_den", ""),
            (metrics2 or {}).get("identity_pct", ""),
            (metrics2 or {}).get("score", ""),
            (metrics2 or {}).get("evalue", ""),
        ),
    ]

    if error_text:
        lines.extend(["", "error", error_text])

    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run_command(cmd: List[str], log_path: str) -> None:
    with open(log_path, "w", encoding="utf-8") as log_handle:
        subprocess.run(cmd, check=True, stdout=log_handle, stderr=subprocess.STDOUT)


def file_has_fasta_records(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(">"):
                return True
    return False


def run_one(cfg_row: Dict[str, str], pair_dir: str, extractor: str, blast_db: str, python_exe: str) -> Dict[str, str]:
    tumor = cfg_row["tumor_sample"]
    run_name = "{tumor}_{chrom}_{pos}_{base}".format(
        tumor=safe_token(tumor),
        chrom=safe_token(cfg_row["chrom"]),
        pos=safe_token(cfg_row["pos1"]),
        base=safe_token(cfg_row["base"]),
    )
    run_dir = os.path.join(pair_dir, run_name)
    os.makedirs(run_dir, exist_ok=True)

    comparison_report = os.path.join(run_dir, "comparison_report.txt")

    try:
        allele1 = cfg_row.get("allele1", "")
        allele2 = cfg_row.get("allele2", "")
        if not allele1 or not allele2:
            status = "no_candidates"
            row = build_summary_row(cfg_row, None, None, "", status, run_dir, comparison_report)
            write_comparison_report(comparison_report, cfg_row, None, None, "", status)
            return row

        extract_prefix = os.path.join(run_dir, "extracted_reads")
        extract_cmd = [
            python_exe,
            extractor,
            "--bam",
            cfg_row["bam"],
            "--chrom",
            cfg_row["chrom"],
            "--pos1",
            str(cfg_row["pos1"]),
            "--base",
            cfg_row["base"],
            "--paired_fa",
            extract_prefix,
            "--normalize_to_ref_fwd",
        ]
        run_command(extract_cmd, os.path.join(run_dir, "extractor.log"))

        r1_fa = extract_prefix + "_R1.fa"
        r2_fa = extract_prefix + "_R2.fa"
        if not file_has_fasta_records(r1_fa) or not file_has_fasta_records(r2_fa):
            status = "no_contigs"
            row = build_summary_row(cfg_row, None, None, "", status, run_dir, comparison_report)
            write_comparison_report(comparison_report, cfg_row, None, None, "", status)
            return row

        megahit_out = os.path.join(run_dir, "megahit")
        megahit_cmd = [
            "megahit",
            "-1",
            r1_fa,
            "-2",
            r2_fa,
            "-o",
            megahit_out,
            "--out-prefix",
            "hla",
        ]
        run_command(megahit_cmd, os.path.join(run_dir, "megahit.log"))

        contigs_candidates = [
            os.path.join(megahit_out, "hla.contigs.fa"),
            os.path.join(megahit_out, "final.contigs.fa"),
        ]
        contigs_path = ""
        for candidate in contigs_candidates:
            if file_has_fasta_records(candidate):
                contigs_path = candidate
                break

        if not contigs_path:
            status = "no_contigs"
            row = build_summary_row(cfg_row, None, None, "", status, run_dir, comparison_report)
            write_comparison_report(comparison_report, cfg_row, None, None, "", status)
            return row

        allele1_fa = os.path.join(run_dir, "allele1.fa")
        allele2_fa = os.path.join(run_dir, "allele2.fa")

        try:
            run_command(
                ["blastdbcmd", "-db", blast_db, "-entry", allele1, "-out", allele1_fa],
                os.path.join(run_dir, "blastdbcmd_allele1.log"),
            )
            run_command(
                ["blastdbcmd", "-db", blast_db, "-entry", allele2, "-out", allele2_fa],
                os.path.join(run_dir, "blastdbcmd_allele2.log"),
            )
        except subprocess.CalledProcessError:
            status = "no_candidates"
            row = build_summary_row(cfg_row, None, None, "", status, run_dir, comparison_report)
            write_comparison_report(comparison_report, cfg_row, None, None, "", status)
            return row

        blast1 = os.path.join(run_dir, "blast_allele1.tsv")
        blast2 = os.path.join(run_dir, "blast_allele2.tsv")

        run_command(
            [
                "blastn",
                "-query",
                contigs_path,
                "-subject",
                allele1_fa,
                "-outfmt",
                "6 nident length pident bitscore evalue",
                "-out",
                blast1,
            ],
            os.path.join(run_dir, "blast_allele1.log"),
        )
        run_command(
            [
                "blastn",
                "-query",
                contigs_path,
                "-subject",
                allele2_fa,
                "-outfmt",
                "6 nident length pident bitscore evalue",
                "-out",
                blast2,
            ],
            os.path.join(run_dir, "blast_allele2.log"),
        )

        metrics1 = parse_blast_metrics(blast1)
        metrics2 = parse_blast_metrics(blast2)

        if metrics1 is None and metrics2 is None:
            status = "missing_blast"
            matching_allele = ""
        else:
            matching_allele = choose_matching_allele(allele1, metrics1, allele2, metrics2)
            status = "tie" if matching_allele == "tie" else "matched"

        row = build_summary_row(cfg_row, metrics1, metrics2, matching_allele, status, run_dir, comparison_report)
        write_comparison_report(comparison_report, cfg_row, metrics1, metrics2, matching_allele, status)
        return row

    except Exception as exc:  # broad exception to keep per-row processing resilient
        status = "error"
        row = build_summary_row(cfg_row, None, None, "", status, run_dir, comparison_report)
        write_comparison_report(comparison_report, cfg_row, None, None, "", status, error_text=str(exc))
        return row


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CLOVER-like HLA allele matching for somatic variants.")
    parser.add_argument("--config", required=True, help="Path to clover_config.tsv generated by prep script")
    parser.add_argument("--pair-dir", required=True, help="Output directory for one tumor-vs-normal pair")
    parser.add_argument("--output", required=True, help="Summary TSV path")
    parser.add_argument("--extractor", default=EXTRACTOR_SCRIPT, help="Path to extract_reads_paired.py")
    parser.add_argument("--blast-db", default=BLAST_DB, help="Path prefix to BLAST DB for HLA alleles")
    parser.add_argument("--python-exe", default="python3", help="Python executable for extractor")
    return parser


def main(argv=None) -> None:
    args = _build_arg_parser().parse_args(argv)
    rows = load_config_rows(args.config)

    os.makedirs(args.pair_dir, exist_ok=True)

    summary_rows = []
    for cfg_row in rows:
        summary_rows.append(
            run_one(
                cfg_row=cfg_row,
                pair_dir=args.pair_dir,
                extractor=args.extractor,
                blast_db=args.blast_db,
                python_exe=args.python_exe,
            )
        )

    write_summary(summary_rows, args.output)


if __name__ == "__main__":
    main()
