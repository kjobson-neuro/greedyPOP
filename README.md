# greedyPOP

**PET-only Centiloid Processing Pipeline**

greedyPOP is a pipeline for calculating Centiloid values from amyloid PET data without requiring a corresponding MRI scan. It is based on the [rPOP (Robust PET-Only Processing)](https://github.com/LeoIacca/rPOP) methodology and uses Greedy for image registration.

## Overview

greedyPOP performs the following steps:
1. **Origin correction** (optional) - Centers the image origin if needed
2. **Skull stripping** - Uses FreeSurfer's SynthStrip for brain extraction
3. **Registration** - Registers PET to tracer-specific templates using Greedy (affine + deformable)
4. **Quality control** - Validates registration quality via Dice score comparison
5. **Smoothing** - Estimates FWHM using AFNI and applies differential smoothing to 10mm target
6. **SUVR calculation** - Computes standardized uptake value ratios using multiple reference regions
7. **Centiloid conversion** - Converts SUVR to Centiloid scale using tracer-specific equations
8. **Visualization** - Generates QC images and ITK-SNAP workspace for review

## Supported Tracers

- **Florbetapir (FBP)** - Amyvid
- **Florbetaben (FBB)** - Neuraceq
- **Flutemetamol (FLUTE)** - Vizamyl

## Reference Regions

Centiloid values are computed using multiple reference regions:
- Whole Cerebellum (WhlCbl)
- Cerebellar Gray Matter (CerebGry)
- Pons
- Whole Cerebellum + Brainstem (WhlCblBrnStm)

## Installation

### Docker (Recommended)

#### Pull from Docker Hub

```bash
docker pull kjobson/greedypop:0.2.0
```

#### Build from Source

```bash
git clone https://github.com/kjobson-neuro/greedyPOP.git
cd greedyPOP
docker build -t greedypop:latest .
```

## Usage

### Docker

```bash
docker run -v /path/to/data:/data \
           -v /path/to/output:/flywheel/v0/output \
           -v /path/to/work:/flywheel/v0/work \
           kjobson/greedypop:0.2.0 \
           -a /data/pet_scan.nii.gz \
           -r Florbetaben \
           -o Keep
```

### Command Line Flags

| Flag | Description | Values |
|------|-------------|--------|
| `-a` | Path to PET data file (required) | NIfTI file path |
| `-r` | Tracer type (required) | `Florbetapir`, `Florbetaben`, `Flutemetamol` |
| `-o` | Origin setting | `Keep` (default), `Reset` |
| `-v` | Verbose mode | (flag only) |
| `-n` | Dry run mode | (flag only) |

### Flag Details

| Flag | Description | Default |
|------|-------------|---------|
| `-o Keep` | Use original image origin | Default |
| `-o Reset` | Reset image origin to center of volume | - |
| `-r Florbetapir` | Use Florbetapir (Amyvid) tracer template and conversion | - |
| `-r Florbetaben` | Use Florbetaben (Neuraceq) tracer template and conversion | - |
| `-r Flutemetamol` | Use Flutemetamol (Vizamyl) tracer template and conversion | - |

## Input

- **PET data**: NIfTI file (`.nii` or `.nii.gz`) or DICOM ZIP archive
  - If multi-volume, motion correction and averaging are applied automatically

## Output

| File | Description |
|------|-------------|
| `sw_pet.nii.gz` | Smoothed, warped PET image |
| `suvr.nii.gz` | SUVR image (whole cerebellum reference) |
| `pyPOP_*.csv` | Results CSV with SUVR and Centiloid values |
| `greedyPOP.itksnap` | ITK-SNAP workspace for visualization |
| `*.png` | QC visualization images |

## Dependencies

greedyPOP relies on the following software (included in Docker image):

- [Python 3.9+](https://www.python.org/)
- [Greedy](https://greedy.readthedocs.io/) - Fast deformable registration
- [AFNI](https://afni.nimh.nih.gov/) - FWHM estimation
- [FreeSurfer 7.4.1](https://surfer.nmr.mgh.harvard.edu/) - SynthStrip skull stripping
- [ITK-SNAP](http://www.itksnap.org/) - Workspace generation
- [NiBabel](https://nipy.org/nibabel/) - NIfTI I/O
- [Nilearn](https://nilearn.github.io/) - Image processing
- [SimpleITK](https://simpleitk.org/) - Image I/O

## Citation

If you use greedyPOP in your research, please cite the original rPOP publication:

> Iaccarino L, Tammewar G, Ayakta N, Baker SL, Bejanin A, Boxer AL, Gorno-Tempini ML, Janabi M, Kramer JH, Lazaris A, Lockhart SN, Miller BL, Miller ZA, O'Neil JP, Ossenkoppele R, Rosen HJ, Schonhaut DR, Jagust WJ, Rabinovici GD. **rPOP: Robust PET-only processing of community acquired heterogeneous amyloid-PET data.** *NeuroImage*. 2022;246:118775. doi: [10.1016/j.neuroimage.2021.118775](https://doi.org/10.1016/j.neuroimage.2021.118775)

## License

MIT License

## Disclaimer

greedyPOP is distributed for academic/research purposes only, with NO WARRANTY. greedyPOP is not intended for any clinical or diagnostic purposes.

## Author

Katie Jobson (k.r.jobson@gmail.com)
