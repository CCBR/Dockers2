
### Changes from v1

- **Installation method**: Installs SPAC directly from GitHub instead of local copy
- **Source repository**: https://github.com/FNLCR-DMAP/SCSAWorkflow
- **Source branch**: `refactor_template_outputs`
- **Package version**: SPAC 0.9.0
- **Templates**: Included via `package_data` in setup.py (umap_tsne_pca, spatial_plot, etc.)


### Key Features

- Fetches `environment.yml` directly from GitHub branch
- Installs SPAC via `pip install git+https://github.com/FNLCR-DMAP/SCSAWorkflow.git@refactor_template_outputs`
- Includes Chromium for Kaleido visualization support
- Headless execution support (QT_QPA_PLATFORM=offscreen, MPLBACKEND=Agg)
- Jupyter notebook support included


| Tool | Version |
|---------|---------|
| git | 2.39.x |
| python3 | 3.9.x |
| spac | 0.9.0 |
| scimap | (from conda channel) |
| scanpy | (from environment.yml) |
| squidpy | (from environment.yml) |
| jupyter | (pip installed) |
| chromium | (for Kaleido) |


### Usage

```bash
# Pull the image
docker pull nciccbr/spac:v2

# Run interactive shell
docker run -it --rm nciccbr/spac:v2 /bin/bash

# Run with data mounted
docker run -it --rm \
    -v /path/to/data:/data \
    -v /path/to/results:/results \
    nciccbr/spac:v2 /bin/bash

# Verify SPAC installation
docker run --rm nciccbr/spac:v2 python -c "import spac; print(spac.__version__)"
```


### Related Links

- SPAC source: https://github.com/FNLCR-DMAP/SCSAWorkflow/tree/refactor_template_outputs
- Templates: https://github.com/FNLCR-DMAP/SCSAWorkflow/tree/refactor_template_outputs/src/spac/templates
