FROM afni/afni_make_build AS afni

FROM --platform=linux/amd64 ubuntu:22.04

# Set environment variables (consolidated)
ENV DEBIAN_FRONTEND="noninteractive" \
    TZ=Etc/UTC \
    LANG="en_US.UTF-8" \
    LC_ALL=C.UTF-8 \
    PYTHONNOUSERSITE=1 \
    FLYWHEEL=/flywheel/v0 \
    OS="Linux" \
    FS_OVERRIDE=0 \
    FIX_VERTEX_AREA="" \
    FSF_OUTPUT_FORMAT="nii.gz" \
    FREESURFER_HOME="/opt/freesurfer" \
    SUBJECTS_DIR="/opt/freesurfer/subjects" \
    FUNCTIONALS_DIR="/opt/freesurfer/sessions" \
    MNI_DIR="/opt/freesurfer/mni" \
    LOCAL_DIR="/opt/freesurfer/local" \
    MINC_BIN_DIR="/opt/freesurfer/mni/bin" \
    MINC_LIB_DIR="/opt/freesurfer/mni/lib" \
    MNI_DATAPATH="/opt/freesurfer/mni/data" \
    PERL5LIB="/opt/freesurfer/mni/lib/perl5/5.8.5" \
    MNI_PERL5LIB="/opt/freesurfer/mni/lib/perl5/5.8.5" \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1

# Install system dependencies (consolidated)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bc \
        binutils \
        build-essential \
        bzip2 \
        ca-certificates \
        cmake \
        curl \
        dcm2niix \
        evince \
        firefox \
        gdb \
        gedit \
        git \
        gnome-terminal \
        gnome-tweaks \
        gnupg \
        gsl-bin \
        jq \
        libatomic1 \
        libcurl4-openssl-dev \
        libgdal-dev \
        libgfortran-11-dev \
        libglu1-mesa-dev \
        libglw1-mesa \
        libgomp1 \
        libjpeg62 \
        libnode-dev \
        libopenblas-dev \
        libssl-dev \
        libtbb2 \
        libudunits2-dev \
        libxml2-dev \
        libxm4 \
        lsb-release \
        netbase \
        netpbm \
        pipx \
        python-is-python3 \
        python3 \
        python3-flask \
        python3-flask-cors \
        python3-matplotlib \
        python3-nibabel \
        python3-numpy \
        python3-pil \
        python3-pip \
        r-base-dev \
        tcsh \
        unzip \
        vim \
        xfonts-100dpi \
        xfonts-base \
        xterm \
        xvfb \
        zip && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy AFNI from multi-stage build
COPY --from=afni /opt /opt

# Install FreeSurfer 7.4.1 - Latest 7.x stable release
# Note: Not using 8.x because it requires 24GB+ RAM vs 8GB for 7.x
RUN curl -sSL https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/7.4.1/freesurfer-linux-ubuntu22_amd64-7.4.1.tar.gz | \
    tar --no-same-owner -xz -C /opt

# Update PATH to include FreeSurfer bin directory
ENV PATH="/opt/freesurfer/bin:$PATH"

# Install ITK-SNAP 4.4.0 for itksnap-wt workspace tool
RUN curl -sSL "https://sourceforge.net/projects/itk-snap/files/itk-snap/4.4.0/itksnap-4.4.0-20250909-Linux-x86_64.tar.gz/download" | \
    tar --no-same-owner -xz -C /opt && \
    mv /opt/itksnap-4.4.0-20250909-Linux-x86_64 /opt/itksnap

# Update PATH for ITK-SNAP
ENV PATH="/opt/itksnap/bin:$PATH"

# Install and set up Miniconda
RUN curl -sSLO https://repo.anaconda.com/miniconda/Miniconda3-py39_25.1.1-2-Linux-x86_64.sh && \
    bash Miniconda3-py39_25.1.1-2-Linux-x86_64.sh -b -p /usr/local/miniconda && \
    rm Miniconda3-py39_25.1.1-2-Linux-x86_64.sh

# Update PATH for Miniconda
ENV PATH="/usr/local/miniconda/bin:$PATH"

# Install conda packages
RUN conda update -y conda && \
    conda install -y --channel conda-forge \
        libgcc-ng \
        libstdcxx-ng \
        matplotlib \
        ncurses \
        nibabel \
        nilearn \
        nipype \
        numpy \
        pytorch \
        python \
        scipy && \
    conda clean -afy

# Install Python packages via pip
RUN pip3 install --no-cache-dir \
        picsl_greedy \
        picsl_c3d \
        simpleitk \
        surfa

# Set library environment variables
ENV LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libgomp.so.1 /usr/lib/x86_64-linux-gnu/libatomic.so.1" \
    MKL_DEBUG_CPU_TYPE=5 \
    LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu:/usr/local/miniconda/lib:$LD_LIBRARY_PATH" \
    GLIBCXX_FORCE_NEW=1

# Create the Flywheel environment
RUN mkdir -p ${FLYWHEEL}

# Copy application files
COPY ./input/ ${FLYWHEEL}/input/
COPY ./workflows/ ${FLYWHEEL}/workflows/
COPY ./pipeline_rPOP.sh ${FLYWHEEL}/
COPY ./rPOP-master ${FLYWHEEL}/rPOP-master
COPY ./workflows/afni.sh ${FLYWHEEL}/workflows/

# Set permissions
RUN chmod -R 777 ${FLYWHEEL}

# Configure entrypoint
ENTRYPOINT ["/bin/bash", "/flywheel/v0/pipeline_rPOP.sh"]
