# greedyPOP

**PET-only Centiloid Processing Pipeline**

greedyPOP is a pipeline for calculating Centiloid values from amyloid PET data without requiring a corresponding MRI scan. It is based on the [rPOP (Robust PET-Only Processing)](https://github.com/LeoIacca/rPOP) methodology and uses Greedy for image registration.

## Overview

greedyPOP performs the following steps:
1. **Origin correction** (optional) - Centers the image origin if needed
2. **Skull stripping** - Uses FreeSurfer's SynthStrip for brain extraction
3. **Registration** - Registers PET to tracer-specific templates using Greedy (affine + deformable)
4. **Quality control** - Validates registration quality via Dice score comparison
5. **Smoothing** - Estimates FWHM using AFNI and applies differential smoothing to target resolution (6mm, 8mm, or 10mm)
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
docker pull kjobson/greedypop:1.3.0
```

#### Build from Source

```bash
git clone https://github.com/kjobson-neuro/greedyPOP.git
cd greedyPOP
docker build --platform linux/amd64 -t kjobson/greedypop:1.3.0 .
```

The image tag should match the `version` in `manifest.json` (and `custom.gear-builder.image`) so the Flywheel gear build stays in sync with the Docker image it wraps.

### Flywheel Gear

greedyPOP is also packaged as a [Flywheel](https://flywheel.io/) gear (see `manifest.json`), built on top of the same `kjobson/greedypop:1.3.0` Docker image.

#### Upload to a Flywheel Instance

Requires the [Flywheel CLI](https://flywheel-io.gitlab.io/product/backend/sdk/branches/master/python/cli.html):

```bash
git clone https://github.com/kjobson-neuro/greedyPOP.git
cd greedyPOP
fw login <your-api-key>
fw gear upload
```

This builds the Docker image and pushes the gear (using the `version` in `manifest.json`) to your Flywheel instance's gear registry, where it becomes available to run on projects you have access to.

## Usage

### Docker

```bash
docker run -v /path/to/data:/flywheel/v0/input \
           -v /path/to/output:/flywheel/v0/output \
           -v /path/to/work:/flywheel/v0/work \
           kjobson/greedypop:1.3.0 \
           -a /flywheel/v0/input/pet_scan.nii.gz \
           -r Florbetaben \
           -t Eight \
           -o Keep
```

### Command Line Flags

| Flag | Description | Values |
|------|-------------|--------|
| `-a` | Path to PET data file (required) | NIfTI file path |
| `-r` | Tracer type (required) | `Florbetapir`, `Florbetaben`, `Flutemetamol` |
| `-t` | Target resolution | `Six` (default), `Eight`, `Ten` |
| `-o` | Origin setting | `Keep` (default), `Reset` |
| `-v` | Verbose mode | (flag only) |

### Flag Details

| Flag | Description | Default |
|------|-------------|---------|
| `-o Keep` | Use original image origin | Default |
| `-o Reset` | Reset image origin to center of volume | - |
| `-r Florbetapir` | Use Florbetapir (Amyvid) tracer template and conversion | - |
| `-r Florbetaben` | Use Florbetaben (Neuraceq) tracer template and conversion | - |
| `-r Flutemetamol` | Use Flutemetamol (Vizamyl) tracer template and conversion | - |
| `-t Six` | Target 6mm FWHM effective resolution | Default |
| `-t Eight` | Target 8mm FWHM effective resolution | - |
| `-t Ten` | Target 10mm FWHM effective resolution | - |

### Flywheel Gear

Once uploaded to your Flywheel instance, greedyPOP can be run from the Flywheel UI or CLI like any other gear.

#### Via the Flywheel UI

1. Navigate to a session containing a PET scan.
2. Select the **greedypop** gear from the gear list.
3. Attach the PET NIfTI file as the `petdata` input.
4. Set the `origin` and `resolution` config options as needed, and select a `tracer` (required — there is no default, since running with the wrong tracer silently produces incorrect Centiloid values).
5. Run the gear.

#### Via the Flywheel CLI

```bash
fw job run greedypop \
    petdata=<file-reference> \
    --project <group>/<project> \
    origin=Keep \
    tracer=Florbetaben \
    resolution=Six
```

#### Gear Config Options

| Config | Description | Values | Default |
|--------|-------------|--------|---------|
| `origin` | Origin setting | `Keep`, `Reset` | `Keep` |
| `tracer` | Tracer type | `Florbetapir`, `Florbetaben`, `Flutemetamol` | None — required |
| `resolution` | Target resolution | `Six`, `Eight`, `Ten` | `Six` |

#### Gear Inputs

| Input | Description | Required |
|-------|-------------|----------|
| `petdata` | PET data file (NIfTI) | Yes |

### Singularity / Apptainer

For HPC environments where Docker is not available, you can convert the Docker image to a Singularity/Apptainer image.

#### Building the Singularity Image

```bash
# Pull from Docker Hub and convert to SIF format
singularity pull greedypop_1.3.0.sif docker://kjobson/greedypop:1.3.0

# Or using Apptainer (newer name for Singularity)
apptainer pull greedypop_1.3.0.sif docker://kjobson/greedypop:1.3.0
```

#### Running with Singularity

```bash
singularity run \
    --bind /path/to/data:/flywheel/v0/input \
    --bind /path/to/output:/flywheel/v0/output \
    --bind /path/to/work:/flywheel/v0/work \
    greedypop_1.3.0.sif \
    -a /flywheel/v0/input/pet_scan.nii.gz \
    -r Florbetaben \
    -t Eight \
    -o Keep
```

#### Running with Apptainer

```bash
apptainer run \
    --bind /path/to/data:/flywheel/v0/input \
    --bind /path/to/output:/flywheel/v0/output \
    --bind /path/to/work:/flywheel/v0/work \
    greedypop_1.3.0.sif \
    -a /flywheel/v0/input/pet_scan.nii.gz \
    -r Florbetaben \
    -t Eight \
    -o Keep
```

#### HPC Cluster Usage (SLURM Example)

```bash
#!/bin/bash
#SBATCH --job-name=greedypop
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00

module load singularity  # or apptainer, depending on your cluster

singularity run \
    --bind $SCRATCH/data:/flywheel/v0/input \
    --bind $SCRATCH/output:/flywheel/v0/output \
    --bind $SCRATCH/work:/flywheel/v0/work \
    $HOME/containers/greedypop_1.3.0.sif \
    -a /flywheel/v0/input/pet_scan.nii.gz \
    -r Florbetapir \
    -t Eight \
    -o Keep
```

## Input

- **PET data**: NIfTI file (`.nii` or `.nii.gz`) or DICOM ZIP archive
  - If multi-volume, motion correction and averaging are applied automatically

## Output

| File | Description |
|------|-------------|
| `sw_pet.nii.gz` | Smoothed, warped PET image (template space) |
| `sw_pet_native.nii.gz` | Smoothed PET image warped back to native space |
| `suvr.nii.gz` | SUVR image in template space (whole cerebellum reference) |
| `suvr_native.nii.gz` | SUVR image warped back to native space |
| `voi_ctx.nii.gz` | Cortical VOI in template space |
| `voi_WhlCbl.nii.gz` | Whole cerebellum VOI in template space |
| `greedyPOP_*.csv` | Results CSV with SUVR, Centiloid values, and FWHM estimates |
| `greedyPOP_QC_*.csv` | QC metrics CSV — asymmetry indices and cerebellar reference sanity checks (see below) |
| `greedyPOP.itksnap` | ITK-SNAP workspace for visualization |
| `SUVR_mosaic.png` | Whole-brain SUVR mosaic |
| `voi_<region>_SUVR_mosaic_prism.png` | Per-VOI SUVR mosaic (one per reference region: `CerebGry`, `ctx`, `Pons`, `WhlCbl`, `WhlCblBrnStm`) |
| `voi_<region>_SUVR_combined.png` | Per-VOI SUVR overlay combined with the VOI outline |
| `WhlCbl_ctx_SUVR_combined.png` | Combined cortical VOI + whole-cerebellum reference overlay |

## Asymmetry & QC Flags

Each run writes a `greedyPOP_QC_*.csv` alongside the results CSV, and prints any flagged warnings to the console. QC logic lives in `workflows/qc.py`; thresholds are placeholders and should be tuned against your own clean scans.

- **Cortical asymmetry index (AI)** — `AI = 100 * (L - R) / ((L + R)/2)`, computed two ways:
  - **Global** (`global_AI_pct`) — over the whole Centiloid cortical VOI, split left/right at its own centroid.
  - **Per lobe** (`Frontal_AI_pct`, `Parietal_AI_pct`, `Temporal_AI_pct`, `Occipital_AI_pct`) — from an MNI-space label atlas split at the midline, to catch focal asymmetry the global VOI would average out.
  - AI is reference-region invariant (the reference cancels out of the ratio), so it's unaffected by which of the four reference regions is used for Centiloid conversion.
  - Flagged (`Asymmetry_flag`) when `|AI|` exceeds `ASYM_AI_ABS_PCT` (default 10%) globally or in any lobe.
- **Cerebellar reference anomaly** (`RefAnomaly_flag`) — the whole-cerebellum / cerebellar-gray uptake ratio (`WhlCbl_to_CerebGry_ratio`) is flagged if it falls outside `[1.05, 1.35]`. A ratio that drifts low can indicate white-matter contamination (Centiloid underestimate); drifting high can indicate cerebellar atrophy or CSF partial-volume effects (Centiloid overestimate).
- **Dice** (`Dice_effective`) — the effective registration Dice score is reported for interpretation, not flagged.

These flags are sanity checks, not diagnostic calls — a flagged scan should be visually reviewed (e.g. via the generated `greedyPOP.itksnap` workspace) rather than automatically excluded.

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
