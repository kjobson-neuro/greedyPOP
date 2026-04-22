#!/bin/bash

## script adapted and uploaded to FW by krj

##
### Script for Executing rPOP
### More information about this pipeline can be found here: https://github.com/LeoIacca/rPOP
### Script pre-processes PET data (without T1w image) for centiloid calculations
##  

# Load config or inputs manually
CmdName=$(basename "$0")
Syntax="${CmdName} [-a PETdata] [-o Origin] [-t Tracer] [-r Resolution ][-v]"
function sys {
        [ -n "${opt_n}${opt_v}" ] && echo "$@" 1>&2
        [ -n "$opt_n" ] || "$@"
}
while getopts a:c:o:t:r:nv arg
do
        case "$arg" in
                a|c|o|t|r)
                        eval "opt_${arg}='${OPTARG}'"
                        ;;
                n|v)
                        eval "opt_${arg}=1"
                        ;;
        esac
done
shift $(( OPTIND - 1 ))  

# Check if there is a config
# If so, load info from config,
# If not, load data manually
if [ -n "$opt_c" ]
then
        ConfigJsonFile="$opt_c"
else
        ConfigJsonFile="${FLYWHEEL:=.}/config.json"
fi

if [ -n "$opt_a" ]; then
        petdata="$opt_a"   
else
        petdata=$( jq '.inputs.petdata.location.path' "$ConfigJsonFile" | tr -d '"' )
fi

if [ -n "$opt_o" ]; then
        Origin="$opt_o"
else
        Origin=$( jq '.config.origin' "$ConfigJsonFile" | tr -d '"' )
fi

if [ -n "$opt_t" ]; then
        Resolution="$opt_t"
else
        Resolution=$( jq '.config.resolution' "$ConfigJsonFile" | tr -d '"' )
fi

if [ -n "$opt_r" ]; then
        Tracer="$opt_r"
else
        Tracer=$( jq '.config.tracer' "$ConfigJsonFile" | tr -d '"' )
fi

# Default resolution to 6mm if not set via command line or config
if [ -z "$Resolution" ] || [ "$Resolution" == "null" ]; then
        Resolution="Six"
fi

### Data Preprocessing
# Set up data paths
flywheel='/flywheel/v0'
rpop_dir='/flywheel/v0/rPOP-master'
data_dir='/flywheel/v0/input'
out_dir='/flywheel/v0/output'
work_dir='/flywheel/v0/work'
exe_dir='/flywheel/v0/workflows'
dcm_dir='/flywheel/v0/work/dcm'

mkdir -p "$flywheel" "$rpop_dir" "$data_dir" "$out_dir" "$work_dir" "$exe_dir" "$dcm_dir"

# Now we need to clean and pass the data to the main script
echo "$Origin origin set."
if [ "$Origin" == "Keep" ]
then
	oropt=1
else
	oropt=2
fi

echo "Tracer is: $Tracer"
case "$Tracer" in
	Florbetapir)
		tracer=1
		;;
	Florbetaben)
		tracer=2
		;;
	Flutemetamol)
		tracer=3
		;;
esac
echo "Resolution is: $Resolution"
case "$Resolution" in
        Six)   
                res=6
                ;;
        Eight)
                res=8
                ;;
        Ten)
                res=10
                ;;
esac

#We need to check out whether or not there are multiple volumes - multiple volumes means we need to pre-process things

if [[ "$petdata" == *.nii.gz ]] || [[ "$petdata" == *.nii ]]; then
        # NIfTI input - copy directly, skip dcm2niix
        echo "Detected NIfTI input - skipping dcm2niix"
        nifti_pet="$petdata"
elif file "$petdata" | grep -q 'Zip archive data'; then
        # DICOM zip
        unzip -d "$dcm_dir" "$petdata"
        dcm2niix -f %d -b y -o "${dcm_dir}/" "$petdata"
        nifti_pet=("${dcm_dir}"/*.nii "${dcm_dir}"/*.nii.gz)
fi

num_vols=$(${FREESURFER_HOME}/bin/mri_info --nframes "${nifti_pet}")
if [[ "${num_vols}" -gt 1 ]]; then
	# Data is a series and needs to be processed
        mcflirt -in "${nifti_pet}" -out "${work_dir}/mc_pet.nii.gz"
        pet_av="${work_dir}/pet_av.nii.gz"
        fslmaths "${work_dir}/mc_pet.nii.gz" -Tmean "${work_dir}/pet_av.nii.gz"
        nifti_pet="${work_dir}/pet_av.nii.gz"
else
        echo "One volume submitted to be processed, co-reg and averaging is assumed to be done."
fi
    
# Run main script with inputs
python3 "${exe_dir}/rPOP.py" -pet "${nifti_pet}" -work "${work_dir}" -out "${out_dir}" -rpop "${rpop_dir}" -origin "${oropt}" -tracer "${tracer}" -exe "${exe_dir}" -fs_path "${FREESURFER_HOME}" -res "${res}"

suvr="${out_dir}/suvr.nii.gz"
list=("voi_CerebGry_2mm" "voi_ctx_2mm" "voi_Pons_2mm" "voi_WhlCbl_2mm" "voi_WhlCblBrnStm_2mm")

# Get visualizations
python3 "${exe_dir}/viz.py" -pet "${suvr}" -mask "${work_dir}/w_pet_mask.nii.gz" -out "${out_dir}" -seg_folder "${rpop_dir}/Centiloid_Std_VOI/nifti/2mm/" -seg "${list[@]}"

voi_dir="${rpop_dir}/Centiloid_Std_VOI/nifti/1mm"

# Create ITK-SNAP workspace for interactive visualization
# To add more images later, use:
#   itksnap-wt -i "${out_dir}/greedyPOP.itksnap" -layers-add-anat <image.nii.gz> -o "${out_dir}/greedyPOP.itksnap"
#   itksnap-wt -i "${out_dir}/greedyPOP.itksnap" -layers-add-seg <segmentation.nii.gz> -o "${out_dir}/greedyPOP.itksnap"
voi_dir="${rpop_dir}/Centiloid_Std_VOI/nifti/2mm"

# Build workspace with one segmentation and cortex as overlay
itksnap-wt \
    -layers-add-seg "${out_dir}/voi_WhlCbl.nii.gz" -tags-add "Whole_Cerebellum" \
    -layers-add-anat "${out_dir}/voi_ctx.nii.gz" -tags-add "Cortex" \
    -layers-set-main "${out_dir}/suvr.nii.gz" -tags-add "SUVR" \
    -layers-add-anat "${out_dir}/sw_pet.nii.gz" -tags-add "Smoothed_PET" \
    -o "${out_dir}/greedyPOP.itksnap"

# Force filesystem sync and verify outputs exist
sync
if [ ! -f "${out_dir}/suvr.nii.gz" ]; then
    echo "ERROR: suvr.nii.gz not found in output directory" >&2
    exit 1
fi
if ! ls "${out_dir}"/*.csv 1>/dev/null 2>&1; then
    echo "ERROR: No CSV files found in output directory" >&2
    exit 1
fi

