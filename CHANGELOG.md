## Dockers2 development version

- New base container for Ubuntu 26.04.

## Dockers2 0.1.2

- Create new containers for RENEE:
    - [arriba](arriba/ccbr_arriba_2.0.0)
    - [bbtools](bbtools/ccbr_bbtools_38.87)
    - [cutadapt](cutadapt/ccbr_cutadapt_1.18)
    - [fastqc](fastqc/ccbr_fastqc_0.11.9)
    - [fastqscreen](fastqscreen/ccbr_fastqscreen_0.14.1)
    - [fastqvalidator](fastqvalidator/ccbr_fastqvalidator_0.1.1)
    - [kraken](kraken/ccbr_kraken_2.1.1/)
    - [preseq](preseq/ccbr_preseq_v2.0/)
    - [qualimap](qualimap/ccbr_qualimap_2.2.1/)
    - [rsem](rsem/ccbr_rsem_1.3.1/)
    - [rseqc](rseqc/ccbr_rseqc_4.0.0/)
    - [ucsc](ucsc/ccbr_ucsc_v385/)
- Update `scripts/tool_version_commands.json` to specify different version commands for each tool.
- Add helper script for combining PRs: `scripts/combine_prs.sh`

## Dockers2 0.1.1

Update to base image. 🥳

- New base containers:
    - [ccbr_ubuntu_22.04:v4](base_images/ccbr_ubuntu_22.04)


## Dockers2 0.1.0

This is the first release of the new and improved dockers repo! 🎉

For the legacy repo, see [CCBR/Dockers](https://github.com/CCBR/dockers).

### features

- New github actions workflows to automatically build and push containers to dockerhub.
- New base containers:
    - [ccbr_ubuntu_20.02:v8](base_images/ccbr_ubuntu_20.02)
    - [ccbr_ubuntu_22.04:v3](base_images/ccbr_ubuntu_22.04)
- New cutadapt containers:
    - [ccbr_cutadapt_1.18:v2](cutadapt/ccbr_cutadapt_1.18)
    - [ccbr_cutadaptt_4.9:v1](cutadapt/ccbr_cutadapt_4.9)
