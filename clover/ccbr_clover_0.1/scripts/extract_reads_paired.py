#!/usr/bin/env python3
import argparse
import pysam
import sys


def revcomp(seq: str) -> str:
    comp = str.maketrans("ACGTNacgtn", "TGCANtgcan")
    return seq.translate(comp)[::-1]


def write_fa(out, name, seq):
    out.write(f">{name}\n{seq}\n")


def build_mate_index(bam_path, ref=None):
    sys.stderr.write("Building full in-memory mate index (may be large)...\n")
    idx = {}
    if ref:
        bam = pysam.AlignmentFile(bam_path, "rb", reference_filename=ref)
    else:
        bam = pysam.AlignmentFile(bam_path, "rb")
    for read in bam.fetch(until_eof=True):
        if read.query_sequence is None:
            continue
        idx.setdefault(read.query_name, []).append(read)
    bam.close()
    sys.stderr.write("Finished building mate index.\n")
    return idx


def find_base_at_pos(read, pos0):
    qpos_at_site = None
    base_at_site = None
    for qpos, rpos in read.get_aligned_pairs(matches_only=False):
        if rpos == pos0:
            if qpos is None:
                base_at_site = None
            else:
                qpos_at_site = qpos
                if read.query_sequence is not None:
                    base_at_site = read.query_sequence[qpos].upper()
            break
    return qpos_at_site, base_at_site


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract reads (keep duplicates) that have a given base at a given reference "
            "position, writing paired FASTA outputs."
        )
    )
    parser.add_argument("--bam", required=True, help="Input BAM/CRAM (CRAM needs --ref)")
    parser.add_argument("--ref", default=None, help="Reference FASTA (required for CRAM)")
    parser.add_argument("--chrom", required=True, help="Chromosome, e.g. chr6")
    parser.add_argument("--pos1", type=int, required=True, help="1-based position")
    parser.add_argument("--base", required=True, help="Desired base at the site")
    parser.add_argument(
        "--paired_fa",
        required=False,
        help="Output FASTA prefix. Produces PREFIX_R1.fa and PREFIX_R2.fa",
    )
    parser.add_argument("--paired_r1", required=False, help="Explicit filename for paired R1 FASTA")
    parser.add_argument("--paired_r2", required=False, help="Explicit filename for paired R2 FASTA")
    parser.add_argument("--min_mapq", type=int, default=0, help="Minimum MAPQ (default 0)")
    parser.add_argument(
        "--normalize_to_ref_fwd",
        action="store_true",
        help="Reverse-complement reverse-strand reads in output to reference-forward orientation",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=0,
        help="If >0, emit only a read-coordinate window around the site; 0 keeps the full read",
    )
    parser.add_argument(
        "--allow_full_mate_scan",
        action="store_true",
        help="Permit a full BAM scan for mate lookup if bam.mate() fails",
    )
    args = parser.parse_args()

    if not (args.paired_fa or (args.paired_r1 and args.paired_r2)):
        parser.error("Specify paired output via --paired_fa PREFIX or both --paired_r1 and --paired_r2")

    pos0 = args.pos1 - 1
    want_base = args.base.upper()

    if args.ref:
        bam = pysam.AlignmentFile(args.bam, "rb", reference_filename=args.ref)
    else:
        bam = pysam.AlignmentFile(args.bam, "rb")

    if args.paired_r1 and args.paired_r2:
        out_r1_path = args.paired_r1
        out_r2_path = args.paired_r2
    else:
        out_r1_path = f"{args.paired_fa}_R1.fa"
        out_r2_path = f"{args.paired_fa}_R2.fa"

    out_r1 = open(out_r1_path, "w", encoding="utf-8")
    out_r2 = open(out_r2_path, "w", encoding="utf-8")

    mate_index = None
    mate_index_built = False
    n_checked = 0
    n_triggers = 0

    try:
        for read in bam.fetch(args.chrom, pos0, pos0 + 1):
            n_checked += 1

            if read.is_unmapped or read.query_sequence is None:
                continue
            if read.mapping_quality < args.min_mapq:
                continue

            qpos, base_at_site = find_base_at_pos(read, pos0)
            if base_at_site != want_base:
                continue

            n_triggers += 1
            qname = read.query_name

            mate = None
            try:
                mate = bam.mate(read)
            except (ValueError, RuntimeError, OSError, IndexError) as exc:
                mate = None
                sys.stderr.write(f"Notice: bam.mate() failed for {qname}: {exc}\n")

            if mate is None and args.allow_full_mate_scan and not mate_index_built:
                mate_index = build_mate_index(args.bam, args.ref)
                mate_index_built = True

            if mate is None and mate_index_built:
                candidates = mate_index.get(qname, [])
                for candidate in candidates:
                    if candidate is not read:
                        mate = candidate
                        break

            seq_trigger = read.query_sequence
            if args.window > 0 and qpos is not None:
                start = max(0, qpos - args.window)
                end = min(len(seq_trigger), qpos + args.window + 1)
                seq_trigger = seq_trigger[start:end]
            if args.normalize_to_ref_fwd and read.is_reverse:
                seq_trigger = revcomp(seq_trigger)

            if getattr(read, "is_read1", False):
                write_fa(out_r1, f"{qname}/1", seq_trigger)
                if mate is not None and mate.query_sequence is not None:
                    seq_mate = mate.query_sequence
                    if args.normalize_to_ref_fwd and mate.is_reverse:
                        seq_mate = revcomp(seq_mate)
                    write_fa(out_r2, f"{qname}/2", seq_mate)
                else:
                    write_fa(out_r2, f"{qname}/2", "")
                    sys.stderr.write(f"Warning: mate (R2) for {qname} not found; wrote placeholder.\n")
            else:
                write_fa(out_r2, f"{qname}/2", seq_trigger)
                if mate is not None and mate.query_sequence is not None:
                    seq_mate = mate.query_sequence
                    if args.normalize_to_ref_fwd and mate.is_reverse:
                        seq_mate = revcomp(seq_mate)
                    write_fa(out_r1, f"{qname}/1", seq_mate)
                else:
                    write_fa(out_r1, f"{qname}/1", "")
                    sys.stderr.write(f"Warning: mate (R1) for {qname} not found; wrote placeholder.\n")
    finally:
        out_r1.close()
        out_r2.close()
        bam.close()

    print(f"Reads overlapping checked: {n_checked}")
    print(f"Triggering reads found and written (duplicates kept): {n_triggers}")
    print(f"Outputs: {out_r1_path} (R1), {out_r2_path} (R2)")


if __name__ == "__main__":
    main()
