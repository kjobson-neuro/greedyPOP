import sys
import os
import logging
import argparse
import nibabel as nb
import shutil
from nibabel.processing import smooth_image
import nilearn
import nilearn.plotting
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec
import matplotlib.image as mpimg
import numpy as np
from scipy import ndimage

parser = argparse.ArgumentParser(description='Take processed images and create visualizations.')

# Set up parser for the CBF file and output directory
parser.add_argument('-pet', type=str, help="The path to the PET file.")
parser.add_argument('-mask', type=str, help="The path to the PET mask.")
parser.add_argument('-out', type=str, help="The output path.")
parser.add_argument('-seg_folder', type=str, help="The path to the ROI files.")
parser.add_argument('-seg', type=str, nargs='+', help="The list of ROI to display.")

args = parser.parse_args()

# Load the images
pet_img = args.pet
pet_nii = nb.load(pet_img)
pet_mask = args.mask
mask_nii = nb.load(pet_mask)
outputdir = args.out

img_data  = pet_nii.get_fdata(dtype=np.float32)      # or float64 if you prefer
mask_data = mask_nii.get_fdata(dtype=np.float32)

# ---- Sanity checks ----
if img_data.shape != mask_data.shape:
    raise ValueError(
        f"Shape mismatch: image {img_data.shape} vs mask {mask_data.shape}"
    )

# ---- Binarise the mask ----
mask_bool = mask_data > 0     # True inside mask, False outside

# ---- Apply the mask ----
# voxels outside the mask get `fill_value`
fill_value = 0.0
masked_data = np.where(mask_bool, img_data, fill_value).astype(img_data.dtype)

# ---- Re‑create a NIfTI object ----
# Use the *image*’s affine so you preserve its spatial orientation
masked_img = nb.Nifti1Image(masked_data, affine=pet_nii.affine, header=pet_nii.header)

# Take the list of segmentations and loop through for vizualizations
seg_folder = args.seg_folder
seg_list = args.seg

for i in seg_list:
    seg_file = os.path.join(seg_folder, i + '.nii')
    seg_nii = nb.load(seg_file)
    seg_name = os.path.basename(seg_file)
    split = seg_name.split('.')
    seg = split[0]

    # Create outline-only version of the ROI mask
    seg_data = seg_nii.get_fdata()
    seg_binary = seg_data > 0
    # Erode the mask and subtract to get only the boundary/outline
    eroded = ndimage.binary_erosion(seg_binary, iterations=1)
    outline_data = (seg_binary.astype(np.float32) - eroded.astype(np.float32))
    outline_nii = nb.Nifti1Image(outline_data, affine=seg_nii.affine, header=seg_nii.header)

    # Plot the SUVR map with two different vmax
    # Note: view_type='contours' is not supported with display_mode='mosaic', so use filled
    nilearn.plotting.plot_roi(seg_nii, masked_img, display_mode='mosaic', black_bg=True, alpha=0.5, cmap="jet", draw_cross=False,
        cut_coords=8, title=f"SUVR_{seg}",
        output_file=os.path.join(outputdir, seg + "_SUVR_mosaic_prism.png"))

    # Combined view: 25 axial slices (5x5 grid) on left, sagittal + coronal stacked on right
    # Save temporary images for each view (using outline mask)
    tmp_axial = os.path.join(outputdir, "_tmp_axial.png")
    tmp_sagittal = os.path.join(outputdir, "_tmp_sagittal.png")
    tmp_coronal = os.path.join(outputdir, "_tmp_coronal.png")

    # Generate 25 axial slices (will be a horizontal strip)
    nilearn.plotting.plot_roi(outline_nii, masked_img, display_mode='z', black_bg=True, alpha=1.0, cmap="jet", draw_cross=False,
        cut_coords=25, title=f"SUVR_{seg}", output_file=tmp_axial)

    nilearn.plotting.plot_roi(outline_nii, masked_img, display_mode='x', black_bg=True, alpha=1.0, cmap="jet", draw_cross=False,
        cut_coords=1, output_file=tmp_sagittal)

    nilearn.plotting.plot_roi(outline_nii, masked_img, display_mode='y', black_bg=True, alpha=1.0, cmap="jet", draw_cross=False,
        cut_coords=1, output_file=tmp_coronal)

    # Load images
    img_axial_strip = mpimg.imread(tmp_axial)
    img_sagittal = mpimg.imread(tmp_sagittal)
    img_coronal = mpimg.imread(tmp_coronal)

    # Reshape axial strip into 5x5 grid (5 rows of 5 slices)
    # The strip contains 25 slices in a row; split into 5 equal parts and stack vertically
    strip_width = img_axial_strip.shape[1]
    slice_width = strip_width // 25
    rows = []
    for row_idx in range(5):
        start_slice = row_idx * 5
        end_slice = start_slice + 5
        start_px = start_slice * slice_width
        end_px = end_slice * slice_width
        row_img = img_axial_strip[:, start_px:end_px, :]
        rows.append(row_img)
    img_axial_grid = np.vstack(rows)

    # Create figure with layout: axial grid on left (5 cols), sagittal+coronal stacked on right (1 col)
    fig = plt.figure(figsize=(20, 12), facecolor='black')
    gs = GridSpec(2, 2, figure=fig, width_ratios=[5, 1], hspace=0.05, wspace=0.05)

    # Left: axial grid (spans both rows)
    ax1 = fig.add_subplot(gs[:, 0])
    ax1.imshow(img_axial_grid)
    ax1.set_facecolor('black')
    ax1.axis('off')

    # Top right: sagittal
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(img_sagittal)
    ax2.set_facecolor('black')
    ax2.axis('off')

    # Bottom right: coronal
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.imshow(img_coronal)
    ax3.set_facecolor('black')
    ax3.axis('off')

    combined_path = os.path.join(outputdir, seg + "_SUVR_combined.png")
    fig.savefig(combined_path, facecolor='black', dpi=150, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    # Clean up temporary files
    os.remove(tmp_axial)
    os.remove(tmp_sagittal)
    os.remove(tmp_coronal)

# Combined WhlCbl + ctx visualization with different colors
whlcbl_file = os.path.join(seg_folder, 'voi_WhlCbl_2mm.nii')
ctx_file = os.path.join(seg_folder, 'voi_ctx_2mm.nii')

if os.path.exists(whlcbl_file) and os.path.exists(ctx_file):
    whlcbl_nii = nb.load(whlcbl_file)
    ctx_nii = nb.load(ctx_file)

    # Create outlines for both ROIs
    whlcbl_data = whlcbl_nii.get_fdata()
    whlcbl_binary = whlcbl_data > 0
    whlcbl_eroded = ndimage.binary_erosion(whlcbl_binary, iterations=1)
    whlcbl_outline = (whlcbl_binary.astype(np.float32) - whlcbl_eroded.astype(np.float32))
    whlcbl_outline_nii = nb.Nifti1Image(whlcbl_outline, affine=whlcbl_nii.affine, header=whlcbl_nii.header)

    ctx_data = ctx_nii.get_fdata()
    ctx_binary = ctx_data > 0
    ctx_eroded = ndimage.binary_erosion(ctx_binary, iterations=1)
    ctx_outline = (ctx_binary.astype(np.float32) - ctx_eroded.astype(np.float32))
    ctx_outline_nii = nb.Nifti1Image(ctx_outline, affine=ctx_nii.affine, header=ctx_nii.header)

    # Create colormaps for each ROI (solid colors)
    cyan_cmap = ListedColormap(['black', 'cyan'])
    red_cmap = ListedColormap(['black', 'red'])

    # Generate temporary images for each ROI with different colors
    tmp_axial_whlcbl = os.path.join(outputdir, "_tmp_axial_whlcbl.png")
    tmp_axial_ctx = os.path.join(outputdir, "_tmp_axial_ctx.png")
    tmp_sag_whlcbl = os.path.join(outputdir, "_tmp_sag_whlcbl.png")
    tmp_sag_ctx = os.path.join(outputdir, "_tmp_sag_ctx.png")
    tmp_cor_whlcbl = os.path.join(outputdir, "_tmp_cor_whlcbl.png")
    tmp_cor_ctx = os.path.join(outputdir, "_tmp_cor_ctx.png")

    # Axial slices - WhlCbl (cyan) and ctx (red)
    nilearn.plotting.plot_roi(whlcbl_outline_nii, masked_img, display_mode='z', black_bg=True, alpha=1.0, cmap=cyan_cmap, draw_cross=False,
        cut_coords=25, title="WhlCbl + ctx", output_file=tmp_axial_whlcbl)
    nilearn.plotting.plot_roi(ctx_outline_nii, masked_img, display_mode='z', black_bg=True, alpha=1.0, cmap=red_cmap, draw_cross=False,
        cut_coords=25, output_file=tmp_axial_ctx)

    # Sagittal slices
    nilearn.plotting.plot_roi(whlcbl_outline_nii, masked_img, display_mode='x', black_bg=True, alpha=1.0, cmap=cyan_cmap, draw_cross=False,
        cut_coords=1, output_file=tmp_sag_whlcbl)
    nilearn.plotting.plot_roi(ctx_outline_nii, masked_img, display_mode='x', black_bg=True, alpha=1.0, cmap=red_cmap, draw_cross=False,
        cut_coords=1, output_file=tmp_sag_ctx)

    # Coronal slices
    nilearn.plotting.plot_roi(whlcbl_outline_nii, masked_img, display_mode='y', black_bg=True, alpha=1.0, cmap=cyan_cmap, draw_cross=False,
        cut_coords=1, output_file=tmp_cor_whlcbl)
    nilearn.plotting.plot_roi(ctx_outline_nii, masked_img, display_mode='y', black_bg=True, alpha=1.0, cmap=red_cmap, draw_cross=False,
        cut_coords=1, output_file=tmp_cor_ctx)

    # Load and composite images (overlay ctx on whlcbl)
    img_axial_whlcbl = mpimg.imread(tmp_axial_whlcbl)
    img_axial_ctx = mpimg.imread(tmp_axial_ctx)
    img_sag_whlcbl = mpimg.imread(tmp_sag_whlcbl)
    img_sag_ctx = mpimg.imread(tmp_sag_ctx)
    img_cor_whlcbl = mpimg.imread(tmp_cor_whlcbl)
    img_cor_ctx = mpimg.imread(tmp_cor_ctx)

    # Composite: where ctx has red, use ctx; otherwise use whlcbl
    # Red channel > 0.5 indicates ctx ROI
    ctx_mask_axial = img_axial_ctx[:, :, 0] > 0.5
    img_axial_combined = img_axial_whlcbl.copy()
    img_axial_combined[ctx_mask_axial] = img_axial_ctx[ctx_mask_axial]

    ctx_mask_sag = img_sag_ctx[:, :, 0] > 0.5
    img_sag_combined = img_sag_whlcbl.copy()
    img_sag_combined[ctx_mask_sag] = img_sag_ctx[ctx_mask_sag]

    ctx_mask_cor = img_cor_ctx[:, :, 0] > 0.5
    img_cor_combined = img_cor_whlcbl.copy()
    img_cor_combined[ctx_mask_cor] = img_cor_ctx[ctx_mask_cor]

    # Reshape axial strip into 5x5 grid
    strip_width = img_axial_combined.shape[1]
    slice_width = strip_width // 25
    rows = []
    for row_idx in range(5):
        start_slice = row_idx * 5
        end_slice = start_slice + 5
        start_px = start_slice * slice_width
        end_px = end_slice * slice_width
        row_img = img_axial_combined[:, start_px:end_px, :]
        rows.append(row_img)
    img_axial_grid = np.vstack(rows)

    # Create combined figure
    fig = plt.figure(figsize=(20, 12), facecolor='black')
    gs = GridSpec(2, 2, figure=fig, width_ratios=[5, 1], hspace=0.05, wspace=0.05)

    ax1 = fig.add_subplot(gs[:, 0])
    ax1.imshow(img_axial_grid)
    ax1.set_facecolor('black')
    ax1.axis('off')

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(img_sag_combined)
    ax2.set_facecolor('black')
    ax2.axis('off')

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.imshow(img_cor_combined)
    ax3.set_facecolor('black')
    ax3.axis('off')

    combined_path = os.path.join(outputdir, "WhlCbl_ctx_SUVR_combined.png")
    fig.savefig(combined_path, facecolor='black', dpi=150, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    # Clean up temporary files
    os.remove(tmp_axial_whlcbl)
    os.remove(tmp_axial_ctx)
    os.remove(tmp_sag_whlcbl)
    os.remove(tmp_sag_ctx)
    os.remove(tmp_cor_whlcbl)
    os.remove(tmp_cor_ctx)

# Now plot the absolute SUVR with discrete scale for visualization
n_colors = 16
base_cmap = plt.get_cmap('jet')
color_list = base_cmap(np.linspace(0, 1, n_colors))
discrete_cmap = ListedColormap(color_list)

nilearn.plotting.plot_stat_map(masked_img, display_mode='mosaic', bg_img=None, black_bg=True, draw_cross=False, cmap=base_cmap,
        cut_coords=8, title="SUVR_mosaic", cbar_tick_format="%i",vmin=0, vmax=3,
        output_file=os.path.join(outputdir, "SUVR_mosaic.png"))

