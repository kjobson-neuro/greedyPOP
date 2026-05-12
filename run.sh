#!/usr/bin/env bash 

IMAGE=kjobson/greedypop:1.0.0

# Command:
docker run -u 0:0 -v /Users/katiejobson/github/gears/greedyPOP/input:/flywheel/v0/input \
	-v /Users/katiejobson/github/gears/greedyPOP/output:/flywheel/v0/output -v \
	/Users/katiejobson/github/gears/greedyPOP/work:/flywheel/v0/work -v \
	/Users/katiejobson/github/gears/greedyPOP/config.json:/flywheel/v0/config.json -v \
	/Users/katiejobson/github/gears/greedyPOP/manifest.json:/flywheel/v0/manifest.json \
	--entrypoint=/bin/sh -e FLYWHEEL='/flywheel/v0' -e \
	PYTHON_GET_PIP_URL='https://github.com/pypa/get-pip/raw/0d8570dc44796f4369b652222cf176b3db6ac70e/public/get-pip.py' \
	-e LANG='en_US.UTF-8' -e PYTHON_VERSION='3.9' -e OS='Linux' -e \
	AFNI_PLUGINPATH='/opt/afni/install' -e \
	PATH='/usr/local/miniconda/bin:/opt/itksnap/bin:/opt/freesurfer/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
	-e DEBIAN_FRONTEND='noninteractive' -e LC_ALL='C.UTF-8' -e PWD='/' -e \
	BASEDIR='/opt/base' -e CONDA_DIR='/opt/miniconda-latest' -e MKL_NUM_THREADS='1' -e \
	OMP_NUM_THREADS='1' -e PYTHONNOUSERSITE='1' -e TZ='Etc/UTC' -e \
	LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu:/usr/local/miniconda/lib:' -e \
	GLIBCXX_FORCE_NEW='1' -e MKL_DEBUG_CPU_TYPE='5' -e \
	LD_PRELOAD='/usr/lib/x86_64-linux-gnu/libgomp.so.1 \
	/usr/lib/x86_64-linux-gnu/libatomic.so.1' -e ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS='1' -e \
	MINC_LIB_DIR='/opt/freesurfer/mni/lib' -e FREESURFER_HOME='/opt/freesurfer' -e \
	MINC_BIN_DIR='/opt/freesurfer/mni/bin' -e FUNCTIONALS_DIR='/opt/freesurfer/sessions' -e \
	PERL5LIB='/opt/freesurfer/mni/lib/perl5/5.8.5' -e MNI_DIR='/opt/freesurfer/mni' -e \
	MNI_PERL5LIB='/opt/freesurfer/mni/lib/perl5/5.8.5' -e LOCAL_DIR='/opt/freesurfer/local' \
	-e FS_OVERRIDE='0' -e FSF_OUTPUT_FORMAT='nii.gz' -e \
	MNI_DATAPATH='/opt/freesurfer/mni/data' -e SUBJECTS_DIR='/opt/freesurfer/subjects' -e \
	OPENBLAS_NUM_THREADS='1' $IMAGE -c /flywheel/v0/pipeline_rPOP.sh \
