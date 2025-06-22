FROM ubuntu:22.04 AS base

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y \
    && apt-get install -y \
        make \
        build-essential \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        wget \
        curl \
        llvm \
        libncurses5-dev \
        libncursesw5-dev \
        xz-utils \
        tk-dev \
        libffi-dev \
        liblzma-dev \
        git \
        bash \
    && rm -rf /var/lib/apt/lists/*


SHELL ["/bin/bash", "-l", "-c"]

ARG UID=0
ARG GID=0
ARG BUILD_OS
ARG USER
RUN if [ "$BUILD_OS" == "linux" ]; then \
  addgroup --gid $GID $USER; \
  adduser --uid $UID --disabled-password --shell /bin/bash --ingroup $USER $USER; \
fi
USER $USER

RUN git clone https://github.com/pyenv/pyenv.git ~/.pyenv && \
  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.profile && \
  echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.profile && \
  echo 'eval "$(pyenv init - bash)"' >> ~/.profile

RUN pyenv install 3.9-dev
RUN pyenv install 3.10-dev
RUN pyenv install 3.11-dev
RUN pyenv install 3.12-dev

COPY --chown=$USER:$USER . /typybench
WORKDIR /typybench

FROM base
ARG REPO
ENV REPO=$REPO
COPY --from=data --chown=$USER:$USER . /typybenchdata/$REPO

RUN if [[ -f "/typybenchdata/$REPO/.python-version" ]]; then \
      pyenv install "$(cat /typybenchdata/$REPO/.python-version)"; \
      cp /typybenchdata/$REPO/.python-version .python-version; \
      else \
      echo "3.12-dev" > .python-version; \
    fi

RUN python3 -m venv venv && source venv/bin/activate && pip install setuptools wheel && pip install -e .

USER root
RUN if [[ -f "/typybenchdata/$REPO/build.sh" ]]; then \
      source venv/bin/activate; \
      cd /typybenchdata/$REPO/original_repo; \
      sh "/typybenchdata/$REPO/build.sh"; \
    fi
USER $USER

RUN if [[ -f "/typybenchdata/$REPO/envs" ]]; then \
      source /typybenchdata/$REPO/envs; \
    fi && \
    if [[ -f "/typybenchdata/$REPO/requirements.txt" ]]; then \
      source venv/bin/activate; \
      cd /typybenchdata/$REPO/original_repo; \
      pip3 install -r "/typybenchdata/$REPO/requirements.txt"; \
    elif [[ -f "/typybenchdata/$REPO/custom_install.sh" ]]; then \
      source venv/bin/activate; \
      cd /typybenchdata/$REPO/original_repo; \
      sh "/typybenchdata/$REPO/custom_install.sh"; \
    elif [[ -f "/typybenchdata/$REPO/original_repo/setup.py" || \
            -f "/typybenchdata/$REPO/original_repo/pyproject.toml" ]]; then \
      source venv/bin/activate; \
      pip3 install -e "/typybenchdata/$REPO/original_repo"; \
    fi

ENTRYPOINT ["/bin/sh", "-c", "/typybench/venv/bin/python3 scripts/evaluation.py -n ${REPO} -p /mnt"]
