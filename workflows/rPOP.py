#!/usr/bin/env python3

import os
import sys
import numpy as np
import nibabel as nb
from scipy import ndimage
from scipy.optimize import minimize
from scipy.spatial.distance import dice as scipy_dice
from datetime import datetime
import nipype
import nipype.interfaces.io as nio
import nipype.pipeline.engine as pe
import subprocess
import argparse
import nilearn
from nilearn import maskers
from nilearn import image
from picsl_greedy import Greedy3D
from picsl_c3d import Convert3D
import SimpleITK as sitk

# Import data
parser = argparse.ArgumentParser(description='Calculate centiloid with only PET data.')

# Set up parser for the PET data and its output
parser.add_argument('-pet', type=str, help="The path to the PET scan.")
parser.add_argument('-work', type=str, help="The path to the work directory.")
parser.add_argument('-rpop', type=str, help="The path to the rPOP master directory.")
parser.add_argument('-origin', type=int, help="Reset origin?")
parser.add_argument('-tracer', type=int, help="Which tracer?")
parser.add_argument('-out', type=str, help="The path to the output directory.")
parser.add_argument('-exe', type=str, help="The path to the directory with executable scripts.")
parser.add_argument('-fs_path', type=str, help="The path to FREESURFER_HOME.")
args = parser.parse_args()

# Load the global input options
input_file = args.pet
work_dir = args.work
rpop_dir = args.rpop
origin = args.origin
tracer = args.tracer
output_dir = args.out
exe_dir = args.exe
temp_dir = os.path.join(rpop_dir, 'templates')
FREESURFER_HOME=args.fs_path

# FUNCTIONS #

# Define function to set origin if set by user
def reset_image_origin(file_path, work_dir):
    c = Convert3D()
    centered_img = f"{work_dir}/img_centered.nii.gz"
    c.execute(f'"{file_path}" -origin-voxel 50% -o "{centered_img}"')

# Extracting values from SUVR via masks - doing this all at once caused RAM usage to go too high, so have to do it by slice
def masked_mean_from_disk(img, mask):
    data = img.dataobj
    mask = mask.dataobj
    total = 0.0
    count = 0
    # iterate by slices to keep peak RAM low
    for z in range(img.shape[2]):
        arr = np.asarray(data[:, :, z], dtype=np.float32)   # pulls just one slice
        m   = np.asarray(mask[:, :, z], dtype=np.uint8)
        vox = arr[m > 0]
        if vox.size:
            total += float(vox.sum())
            count += int(vox.size)
    return (total / count) if count else np.nan
    
# Dice score to evaluate the registration semi-automatically
def dice_score(mask1, mask2):
# Load the NIfTI files
    mask1_img = nb.load(mask1)
    mask2_img = nb.load(mask2)
    
    # Get the data arrays
    mask1_data = mask1_img.get_fdata()
    mask2_data = mask2_img.get_fdata()
    
    # Flatten the arrays
    mask1_flat = mask1_data.flatten()
    mask2_flat = mask2_data.flatten()

    # Calculate Dice dissimilarity using scipy
    dissimilarity = scipy_dice(mask1_flat, mask2_flat)

    # Convert to similarity score (Dice coefficient) and return as percentage
    similarity = (1 - dissimilarity) * 100
    
    return similarity

# If registration does not work, we try again with all brains skull-stripped
def stripped_registration(pet_scan, pet_mask, warptempl, warptempl_mask):
    # Redo the registration if dice score < .90
    # Do registration after skullstripping - keeping the rigid registration and onwards
    g = Greedy3D()    

    # Rigid registration
    r_prefix = 'rigid'
    
    # Load the data
    img_fixed = sitk.ReadImage(warptempl)
    img_moving = sitk.ReadImage(pet_scan)
    fixed_mask = sitk.ReadImage(warptempl_mask)
    moving_mask = sitk.ReadImage(pet_mask)

    g.execute('-threads 1 '
           ' -i my_fixed my_moving '
           '-ia-image-centers '
           '-gm fmask '
           '-mm mmask ' 
           '-a -dof 6 -n 200x80x20 -m MI '
           '-o rigid',
           my_fixed = img_fixed, my_moving = img_moving, fmask = fixed_mask, mmask = moving_mask,
           rigid = None)
    
    g.execute('-threads 1 '
          '-rf my_fixed '
          '-rm my_moving rwarpedimg '
          '-r rigid',
          rwarpedimg=None)
    
    # Save the images so we can check out if something went wrong    
    rwarped_img = os.path.join(work_dir, f'{r_prefix}.nii.gz')  
    sitk.WriteImage(g['rwarpedimg'], rwarped_img)
    
    # Perform affine registration
    # Change the name to avoid re-writing
    prefix = 'redo_init_reg'
    
    img_moving = sitk.ReadImage(rwarped_img)
    fixed_mask = sitk.ReadImage(warptempl_mask)
    
    g.execute('-threads 1 '
           ' -i my_fixed my_moving '
           '-ia-image-centers '
           '-gm fmask '
           '-a -dof 12 -n 100x40x10 -m MI '
           '-o redo_affine', 
           my_fixed = img_fixed, my_moving = img_moving, fmask = fixed_mask,
           redo_affine = None)
           
    g.execute('-threads 1 '
          '-rf my_fixed '
          '-rm my_moving warpedimg '
          '-r redo_affine',   
          warpedimg=None)
          
    warped_img = os.path.join(work_dir, f'{prefix}.nii.gz')
    sitk.WriteImage(g['warpedimg'], warped_img)
    
    # Load data for full deformed reg
    init_path = os.path.join(work_dir, "redo_init_reg.nii.gz")
    img_moving_def = sitk.ReadImage(init_path)

    # Warp the image to MNI space using Greedy
    # Allowing it to write over the old w_pet image here because it will be cleaner for output and we already know that it had a bad registration
    full_prefix = 'w_pet'
    deformedimg = os.path.join(work_dir, f'{full_prefix}.nii.gz')
    # Perform registration
    g.execute('-threads 1 '
          '-i my_fixed my_moving '  
          '-n 100x40x10 -s 20.0vox 10.0vox '
          '-gm fmask '
          '-m WNCC 3x3x3 '
          '-svlb '
          '-o redo_deformed ',
           my_fixed = img_fixed, my_moving = img_moving_def,  fmask = fixed_mask,
           redo_deformed = None)
    
    # Reslice
    g.execute('-threads 1 '
              ' -rf my_fixed '
              ' -rm my_moving deformedimg '
          '-r redo_deformed',
          deformedimg = None)
    
    sitk.WriteImage(g['deformedimg'] , deformedimg)

# Define the main function
def rPOP(input_file, output_dir, set_origin, tracer, work_dir, temp_dir):
    print("\n\n********** Welcome to greedyPOP v1.0 (September 2025) **********")
    print("greedyPOP is dependent on:")
    print("*1. Python (https://www.python.org/)")
    print("*2. Greedy: Fast Deformable Registration for 2D and 3D Medical Images (https://greedy.readthedocs.io/en/latest/index.html)")
    print("*3. AFNI Neuroimaging Suite (https://afni.nimh.nih.gov/)")
    print("*4. FreeSurfer's SynthStrip (https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/)")
    print("*** greedyPOP is only distributed for academic/research purposes, with NO WARRANTY. ***")
    print("*** greedyPOP is not intended for any clinical or diagnostic purposes. ***")

    # Load greedy here for memory reasons
    from picsl_greedy import Greedy3D
    g = Greedy3D()

    # Load the templates
    warptempl_fbp = os.path.join(temp_dir, 'Template_FBP_all.nii')
    warptempl_fbb = os.path.join(temp_dir, 'Template_FBB_all.nii')
    warptempl_flute = os.path.join(temp_dir, 'Template_FLUTE_all.nii')

    # Reset origin to center of image if it's set
    if set_origin == 2:
        print("Resetting origin")
        reset_image_origin(input_file, work_dir)
    elif set_origin == 1:
        print("Keeping original origin")
        data = nb.load(input_file)
        nb.save(data, f'{work_dir}/img_centered.nii.gz')
    else:
        raise ValueError(f"Unexpected origin setting: {set_origin}")

    centered_img = os.path.join(work_dir, 'img_centered.nii.gz')
    centered_mask = os.path.join(work_dir, 'mask_centered.nii.gz')
    centered_output = os.path.join(work_dir, 'stripped_centered.nii.gz')
    subprocess.run([f'{FREESURFER_HOME}/bin/mri_synthstrip',
         '-i', f'{centered_img}',
         '-m', f'{centered_mask}',
         '-o', f'{centered_output}'],
         check=True
         )

    # Template choice
    if tracer == 1:
        warptempl = warptempl_fbp
    elif tracer == 2:
        warptempl = warptempl_fbb
    elif tracer == 3:
        warptempl = warptempl_flute

    print(f"Template used for registration: {warptempl}")

    # Load data
    temp_mask_path = os.path.join(temp_dir, 'temp_mask.nii.gz')

    # Perform affine registration    
    prefix = 'init_reg'

    img_fixed = sitk.ReadImage(warptempl)
    img_moving = sitk.ReadImage(centered_img)
    fixed_mask = sitk.ReadImage(temp_mask_path)
    moving_mask = sitk.ReadImage(centered_mask)

    # Create mat image to save affine transform
    affine_mat = os.path.join(work_dir, f'{prefix}.mat')

    g.execute('-threads 1 '
           ' -i my_fixed my_moving '
           '-ia-image-centers '
           '-gm fmask '
           '-mm mmask '
           '-a -dof 12 -n 100x40x10 -m MI '
           '-o affine',
           my_fixed = img_fixed, my_moving = img_moving, fmask = fixed_mask, mmask = moving_mask,
           affine = None)

    g.execute('-threads 1 '
          '-rf my_fixed '
          '-rm my_moving warpedimg '
          '-r affine',
          warpedimg=None)

    warped_img = os.path.join(work_dir, f'{prefix}.nii.gz')
    sitk.WriteImage(g['warpedimg'], warped_img)
    np.savetxt(affine_mat, g['affine'])

    # Load data for full deformed reg
    init_path = os.path.join(work_dir, "init_reg.nii.gz")
    img_moving_def = sitk.ReadImage(init_path)

    # Warp the image to template space using Greedy
    full_prefix = 'w_pet'
    deformedimg = os.path.join(work_dir, f'{full_prefix}.nii.gz')
    deform_warp = os.path.join(work_dir, f'{full_prefix}_warp.nii.gz')
    # Perform registration
    g.execute('-threads 1 '
          '-i my_fixed my_moving '
          '-n 100x40x10 -s 20.0vox 10.0vox '
          '-m WNCC 3x3x3 '
          '-sv '
          '-o deformed_affine ',
           my_fixed = img_fixed, my_moving = img_moving_def, 
           deformed_affine = None)

    # Reslice
    g.execute('-threads 1 '
              ' -rf my_fixed '
              ' -rm my_moving deformedimg '
          '-r deformed_affine ',
          deformedimg = None, inverse_warp=None)

    sitk.WriteImage(g['deformedimg'], deformedimg)
    sitk.WriteImage(g['deformed_affine'], deform_warp)

    # Invert the warp field using greedy (must use file paths for vector images)
    deform_inv_warp = os.path.join(work_dir, f'{full_prefix}_inverse_warp.nii.gz')
    g.execute(f'-threads 1 '
              f'-iw {deform_warp} {deform_inv_warp} ')

    w_pet_mask = os.path.join(work_dir, 'w_pet_mask.nii.gz')
    w_pet_brain = os.path.join(work_dir, 'w_pet_brain.nii.gz')
    subprocess.run([f'{FREESURFER_HOME}/bin/mri_synthstrip',
         '-i', f'{deformedimg}',
         '-m', f'{w_pet_mask}',
         '-o', f'{w_pet_brain}'],
         check=True
         )
    
    # Check if the masks overlap more than .9
    dice_score_masks= dice_score(w_pet_mask, temp_mask_path)
    if dice_score_masks > 90:
        print(f"Dice score was {dice_score_masks}, continuing to AFNI smoothing.")
    else:
        # This function overwrites the w_pet image so we don't have to change anything moving forward
        stripped_registration(centered_img, centered_mask, warptempl, temp_mask_path)        
        redo_origin_deformed = os.path.join(work_dir, 'w_pet.nii.gz')
        redo_w_pet_mask = os.path.join(work_dir, 'w_pet_mask.nii.gz')
        redo_w_pet_brain = os.path.join(work_dir, 'w_pet_brain.nii.gz')
        subprocess.run([f'{FREESURFER_HOME}/bin/mri_synthstrip',
            '-i', f'{redo_origin_deformed}',
            '-m', f'{redo_w_pet_mask}',
            '-o', f'{redo_w_pet_brain}'],
            check=True
            )    
        dice_score_stripped = dice_score(w_pet_mask, temp_mask_path)
        if dice_score_stripped > 90:
            print(f"Dice score is sufficient with skull-stripped registration: {dice_score_masks}")
            print("Continuing with smoothing, SUVR and centiloid calculations.")
        else:
            dice_change = dice_score_stripped - dice_score_masks
            print(f"New dice score is {dice_score_stripped}, which is {dice_change} larger than previous.")
            print("Dice score did not improve enough, the registration has failed. Cannot compute centiloid. Exiting program.")
            sys.exit()

    # Unload data to free memory
    import gc
    del g
    gc.collect()

    # Estimate FWHM using AFNI's 3dFWHMx
    afni_out = 'sw_pet_afni'
    subprocess.run([f"{exe_dir}/afni.sh",
                f"{work_dir}", f"{afni_out}"])

    fwhm_file = f'{work_dir}/sw_pet_afni_automask.txt'
    # Read FWHM estimations
    fwhm_data = np.loadtxt(fwhm_file)

    # Extract only the first row for old FWHM calc
    fwhm_x, fwhm_y, fwhm_z = fwhm_data[0, 0:3]

    # Calculate smoothing filters
    def calc_filter(fwhm):
        return np.sqrt(max(0, 10**2 - fwhm**2)) if fwhm < 10 else 0

    filter_x = calc_filter(fwhm_x)
    filter_y = calc_filter(fwhm_y)
    filter_z = calc_filter(fwhm_z)

    # Apply smoothing
    sigma = (filter_x / 2.355, filter_y / 2.355, filter_z / 2.355)

    smoothed_prefix = 'sw_pet'
    smoothed_img = nilearn.image.smooth_img(deformedimg,fwhm=[filter_x, filter_y, filter_z])  # Direct FWHM input in mm
    nb.save(smoothed_img, f'{output_dir}/{smoothed_prefix}.nii.gz')

    del deformedimg
    gc.collect()

    # Calculate wtx
    ctx = os.path.join(rpop_dir, 'Centiloid_Std_VOI/nifti/1mm', 'voi_ctx_1mm.nii')
    ctx_img = nb.load(ctx)

    wc = os.path.join(rpop_dir, 'Centiloid_Std_VOI/nifti/1mm', 'voi_WhlCbl_1mm.nii')  
    wc_img = nb.load(wc)

    wcgm = os.path.join(rpop_dir, 'Centiloid_Std_VOI/nifti/1mm', 'voi_CerebGry_1mm.nii')
    wcgm_img = nb.load(wcgm)

    pons = os.path.join(rpop_dir, 'Centiloid_Std_VOI/nifti/1mm', 'voi_Pons_1mm.nii')
    pons_img = nb.load(pons)

    wcbs = os.path.join(rpop_dir, 'Centiloid_Std_VOI/nifti/1mm', 'voi_WhlCblBrnStm_1mm.nii')
    wcbs_img = nb.load(wcbs)

    smoothed_data = smoothed_img.get_fdata(dtype=np.float32)
 
    from nilearn.image import resample_to_img
    ctx_resamp = resample_to_img(ctx_img, smoothed_img, interpolation="nearest", copy_header=True)
    wc_resamp = resample_to_img(wc_img, smoothed_img, interpolation="nearest", copy_header=True)
    wcgm_resamp = resample_to_img(wcgm_img, smoothed_img, interpolation="nearest", copy_header=True)
    pons_resamp = resample_to_img(pons_img, smoothed_img, interpolation="nearest", copy_header=True)
    wcbs_resamp = resample_to_img(wcbs_img, smoothed_img, interpolation="nearest", copy_header=True)

    avg_ctx_voi_bin = masked_mean_from_disk(smoothed_img, ctx_resamp)
    avg_wc_voi_bin  = masked_mean_from_disk(smoothed_img, wc_resamp)
    avg_wcgm_voi_bin  = masked_mean_from_disk(smoothed_img, wcgm_resamp)
    avg_pons_voi_bin  = masked_mean_from_disk(smoothed_img, pons_resamp)
    avg_wcbs_voi_bin  = masked_mean_from_disk(smoothed_img, wcbs_resamp)

    if not np.isfinite(avg_wc_voi_bin) or avg_wc_voi_bin == 0:
    	raise ValueError("Reference mask is empty or zero — cannot compute SUVR.")
    neoSUVR_wc = float(avg_ctx_voi_bin / avg_wc_voi_bin)
    neoSUVR_wcgm = float(avg_ctx_voi_bin / avg_wcgm_voi_bin)
    neoSUVR_pons = float(avg_ctx_voi_bin / avg_pons_voi_bin)
    neoSUVR_wcbs = float(avg_ctx_voi_bin / avg_wcbs_voi_bin)

    if tracer == 1: 
        FBPCL_wc = ((189.9 * neoSUVR_wc) - 211.1)
        centiloid_wc = FBPCL_wc
        FBPCL_wcgm = ((189.9 * neoSUVR_wcgm) - 211.1)
        centiloid_wcgm = FBPCL_wcgm
        FBPCL_pons = ((189.9 * neoSUVR_pons) - 211.1)
        centiloid_pons = FBPCL_pons
        FBPCL_wcbs = ((189.9 * neoSUVR_wcbs) - 211.1)
        centiloid_wcbs = FBPCL_wcbs
    elif tracer == 2:    
        FBBCL_wc = ((160.7 * neoSUVR_wc) - 169.2)
        centiloid_wc = FBBCL_wc
        FBBCL_wcgm = ((160.7 * neoSUVR_wcgm) - 169.2)
        centiloid_wcgm = FBBCL_wcgm
        FBBCL_pons = ((160.7 * neoSUVR_pons) - 169.2)
        centiloid_pons = FBBCL_pons
        FBBCL_wcbs = ((160.7 * neoSUVR_wcbs) - 169.2)
        centiloid_wcbs = FBBCL_wcbs
    elif tracer == 3:     
        FLUTECL_wc = ((127.6 * neoSUVR_wc) - 136.2)
        centiloid_wc = FLUTECL_wc
        FLUTECL_wcgm = ((127.6 * neoSUVR_wcgm) - 136.2)
        centiloid_wcgm = FLUTECL_wcgm
        FLUTECL_pons = ((127.6 * neoSUVR_pons) - 136.2)
        centiloid_pons = FLUTECL_pons
        FLUTECL_wcbs = ((127.6 * neoSUVR_wcbs) - 136.2)
        centiloid_wcbs = FLUTECL_wcbs

    # Create SUVR image
    suv_temp = os.path.join(work_dir, 'w_pet_brain.nii.gz')
    suv_data = nb.load(suv_temp)   

    # Calculate cerebellum mean using your slice-by-slice function
    wc_mean = masked_mean_from_disk(suv_data, wc_resamp)  

    if wc_mean == 0 or np.isnan(wc_mean):
       print(f"  Cerebellum mean is 0 or NaN. SUVR image not calculated. Cerebellum mean is: {wc_mean}")
    else:
       # Create SUVR image slice-by-slice to keep memory usage low
       suvr_data = np.zeros(suv_data.shape, dtype=np.float32)
       data = suv_data.dataobj
    
       for z in range(suv_data.shape[2]):
            slice_data = np.asarray(data[:, :, z], dtype=np.float32)
            suvr_data[:, :, z] = slice_data / wc_mean
    
    # Create new NIfTI image with the same header/affine as the original
    suvr_image = nb.Nifti1Image(suvr_data, suv_data.affine, suv_data.header)
    suvr_file = os.path.join(output_dir, 'suvr.nii.gz')
    nb.save(suvr_image, suvr_file)

    # Warp SUVR and sw_pet back to native space using inverse transforms
    g = Greedy3D()
    native_ref = sitk.ReadImage(centered_img)

    # SUVR to native space (use file paths for warp since vector images not supported in-memory)
    # Use greedy's native inversion syntax (,-1) for affine, and apply in correct order
    suvr_sitk = sitk.ReadImage(suvr_file)
    suvr_native_file = os.path.join(output_dir, 'suvr_native.nii.gz')
    g.execute(f'-threads 1 '
              f'-rf ref_img '
              f'-rm moving_img out_img '
              f'-r {affine_mat},-1 {deform_inv_warp} ',
              ref_img=native_ref, moving_img=suvr_sitk,
              out_img=None)
    sitk.WriteImage(g['out_img'], suvr_native_file)

    # sw_pet to native space
    sw_pet_file = os.path.join(output_dir, f'{smoothed_prefix}.nii.gz')
    sw_pet_sitk = sitk.ReadImage(sw_pet_file)
    sw_pet_native_file = os.path.join(output_dir, 'sw_pet_native.nii.gz')
    g.execute(f'-threads 1 '
              f'-rf ref_img '
              f'-rm moving_img out_img '
              f'-r {affine_mat},-1 {deform_inv_warp} ',
              ref_img=native_ref, moving_img=sw_pet_sitk,
              out_img=None)
    sitk.WriteImage(g['out_img'], sw_pet_native_file)

    del g
    gc.collect()

    # Save results to CSV
    results = {
        'subjectID': ['sw_pet.nii.gz'],
        'avg_ctx_voi_bin': [avg_ctx_voi_bin],
        'avg_wc_voi_bin': [avg_wc_voi_bin],
        'WhlCbl_NeocorticalSUVR': [neoSUVR_wc],
        'WhlCbl_Centiloid': [centiloid_wc],
        'CerebGry_NeocorticalSUVR': [neoSUVR_wcgm],
        'CerebGry_Centiloid': [centiloid_wcgm],
        'Pons_NeocorticalSUVR': [neoSUVR_pons],
        'Pons_Centiloid': [centiloid_pons],
        'WhlCblBrnStm_NeocorticalSUVR': [neoSUVR_wcbs],
        'WhlCblBrnStm_Centiloid': [centiloid_wcbs],
        'EstimatedFWHMx': [fwhm_x],
        'EstimatedFWHMy': [fwhm_y],
        'EstimatedFWHMz': [fwhm_z],
        'FWHMfilterappliedx': [filter_x],
        'FWHMfilterappliedy': [filter_y],
        'FWHMfilterappliedz': [filter_z]
    }
    import pandas as pd
    print(results)
    df = pd.DataFrame(results)
    csv_file = os.path.join(output_dir, f'pyPOP_{datetime.now().strftime("%m-%d-%Y_%H-%M-%S")}.csv')
    df.to_csv(csv_file, index=False)

    print("\nPYrPOP just finished! Warped and differentially smoothed AC PET images were generated.")
    print("Lookup the .csv database to assess FWHM estimations and filters applied.\n")

# Execute:
rPOP(input_file, output_dir, origin, tracer, work_dir, temp_dir)

