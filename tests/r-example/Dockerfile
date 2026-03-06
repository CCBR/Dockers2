FROM rocker/tidyverse:4.3.2

# build time variables
ARG BUILD_DATE="000000"
ENV BUILD_DATE=${BUILD_DATE}
ARG BUILD_TAG="000000"
ENV BUILD_TAG=${BUILD_TAG}
ARG REPONAME="000000"
ENV REPONAME=${REPONAME}

SHELL ["/bin/bash", "-lc"]

RUN chmod 777 /usr/local/lib/R/site-library /usr/local/lib/R/library

# install R package
COPY . /opt2/example
RUN R -e "remotes::install_local('/opt2/example', dependencies = TRUE, upgrade='always', repos='http://cran.rstudio.com'); library(example); readr::write_tsv(tibble::as_tibble(installed.packages()), '/mnt/r-packages.tsv')"

# add example exec to the path
RUN chmod -R +x /usr/local/lib/R/site-library/example/exec
ENV PATH="$PATH:/usr/local/lib/R/site-library/example/exec"
RUN example

# Save Dockerfile in the docker
COPY Dockerfile /opt2/Dockerfile_${REPONAME}.${BUILD_TAG}
RUN chmod a+r /opt2/Dockerfile_${REPONAME}.${BUILD_TAG}

# cleanup
WORKDIR /data2
RUN apt-get clean && apt-get purge \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
