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

def crop_black_borders(img, threshold=0.15, padding=5):
    """Crop black borders from an image, keeping a small padding."""
    if img.ndim == 3:
        # Use max across RGB to detect any non-black content
        gray = np.max(img[:, :, :3], axis=2)
    else:
        gray = img
    rows = np.any(gray > threshold, axis=1)
    cols = np.any(gray > threshold, axis=0)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    rmin = max(0, rmin - padding)
    rmax = min(img.shape[0], rmax + padding)
    cmin = max(0, cmin - padding)
    cmax = min(img.shape[1], cmax + padding)
    return img[rmin:rmax, cmin:cmax]

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

# Load cerebellar reference ROI (WhlCbl) for combined visualizations
whlcbl_ref_file = os.path.join(seg_folder, 'voi_WhlCbl_2mm.nii')
whlcbl_ref_nii = None
whlcbl_ref_outline_nii = None
if os.path.exists(whlcbl_ref_file):
    whlcbl_ref_nii = nb.load(whlcbl_ref_file)
    whlcbl_ref_data = whlcbl_ref_nii.get_fdata()
    whlcbl_ref_binary = whlcbl_ref_data > 0
    whlcbl_ref_eroded = ndimage.binary_erosion(whlcbl_ref_binary, iterations=1)
    whlcbl_ref_outline = (whlcbl_ref_binary.astype(np.float32) - whlcbl_ref_eroded.astype(np.float32))
    whlcbl_ref_outline_nii = nb.Nifti1Image(whlcbl_ref_outline, affine=whlcbl_ref_nii.affine, header=whlcbl_ref_nii.header)

# Create colormaps for ROI visualization
cyan_cmap = ListedColormap(['black', 'cyan'])  # For cerebellar reference
red_cmap = ListedColormap(['black', 'red'])    # For target ROI

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
    # Shows both target ROI (red) and cerebellar reference (cyan)

    # Create a combined labeled mask: 1 = cerebellar ref (cyan), 2 = target ROI (red)
    is_whlcbl = 'WhlCbl' in seg
    if whlcbl_ref_outline_nii is not None and not is_whlcbl:
        # Combine both outlines into one labeled image
        combined_outline = np.zeros_like(outline_data)
        combined_outline[whlcbl_ref_outline > 0] = 1  # Cerebellar = 1 (cyan)
        combined_outline[outline_data > 0] = 2        # Target ROI = 2 (red), overwrites overlap
        combined_outline_nii = nb.Nifti1Image(combined_outline, affine=seg_nii.affine, header=seg_nii.header)
        # Colormap: 0=transparent, 1=cyan, 2=red
        combined_cmap = ListedColormap(['black', 'cyan', 'red'])
    else:
        # Just the target ROI
        combined_outline_nii = outline_nii
        combined_cmap = red_cmap

    tmp_axial = os.path.join(outputdir, "_tmp_axial.png")
    tmp_sag = os.path.join(outputdir, "_tmp_sag.png")
    tmp_cor = os.path.join(outputdir, "_tmp_cor.png")

    # Generate slices with combined ROI mask
    nilearn.plotting.plot_roi(combined_outline_nii, masked_img, display_mode='z', black_bg=True, alpha=1.0, cmap=combined_cmap, draw_cross=False,
        cut_coords=25, colorbar=False, output_file=tmp_axial)
    nilearn.plotting.plot_roi(combined_outline_nii, masked_img, display_mode='x', black_bg=True, alpha=1.0, cmap=combined_cmap, draw_cross=False,
        cut_coords=[5], colorbar=False, annotate=False, output_file=tmp_sag)
    nilearn.plotting.plot_roi(combined_outline_nii, masked_img, display_mode='y', black_bg=True, alpha=1.0, cmap=combined_cmap, draw_cross=False,
        cut_coords=1, colorbar=False, annotate=False, output_file=tmp_cor)

    # Load images
    img_axial_combined = mpimg.imread(tmp_axial)
    img_sag_combined = crop_black_borders(mpimg.imread(tmp_sag))
    img_cor_combined = crop_black_borders(mpimg.imread(tmp_cor))

    # Reshape axial strip into 5x5 grid (5 rows of 5 slices)
    # The strip contains 25 slices in a row; split into 5 equal parts and stack vertically
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

    # Create figure with layout: axial grid on left, sagittal+coronal stacked on right
    # Using width_ratios=[3, 2] to give more space to sagittal/coronal views
    fig = plt.figure(figsize=(24, 14), facecolor='black')
    gs = GridSpec(2, 2, figure=fig, width_ratios=[3, 2], hspace=0.02, wspace=0.02)

    # Left: axial grid (spans both rows)
    ax1 = fig.add_subplot(gs[:, 0])
    ax1.imshow(img_axial_grid)
    ax1.set_facecolor('black')
    ax1.axis('off')
    # Shrink each axes box to its image's aspect ratio so no black padding is
    # added, then anchor: grid to the right edge of the left column ('E'),
    # sagittal/coronal to the left edge of the right column ('W'). This removes
    # the blank space between the axial grid and the sagittal/coronal views.
    ax1.set_box_aspect(img_axial_grid.shape[0] / img_axial_grid.shape[1])
    ax1.set_anchor('E')

    # Top right: sagittal (5 slices stacked)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(img_sag_combined)
    ax2.set_facecolor('black')
    ax2.axis('off')
    ax2.set_box_aspect(img_sag_combined.shape[0] / img_sag_combined.shape[1])
    ax2.set_anchor('W')

    # Bottom right: coronal (5 slices stacked)
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.imshow(img_cor_combined)
    ax3.set_facecolor('black')
    ax3.axis('off')
    ax3.set_box_aspect(img_cor_combined.shape[0] / img_cor_combined.shape[1])
    ax3.set_anchor('W')

    combined_path = os.path.join(outputdir, seg + "_SUVR_combined.png")
    fig.savefig(combined_path, facecolor='black', dpi=150, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    # Clean up temporary files
    os.remove(tmp_axial)
    os.remove(tmp_sag)
    os.remove(tmp_cor)

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

    ctx_data = ctx_nii.get_fdata()
    ctx_binary = ctx_data > 0
    ctx_eroded = ndimage.binary_erosion(ctx_binary, iterations=1)
    ctx_outline = (ctx_binary.astype(np.float32) - ctx_eroded.astype(np.float32))

    # Create combined labeled mask: 1 = WhlCbl (cyan), 2 = ctx (red)
    combined_outline = np.zeros_like(whlcbl_outline)
    combined_outline[whlcbl_outline > 0] = 1  # WhlCbl = 1 (cyan)
    combined_outline[ctx_outline > 0] = 2      # ctx = 2 (red), overwrites overlap
    combined_outline_nii = nb.Nifti1Image(combined_outline, affine=whlcbl_nii.affine, header=whlcbl_nii.header)

    # Colormap: 0=transparent, 1=cyan, 2=red
    combined_cmap = ListedColormap(['black', 'cyan', 'red'])

    tmp_axial = os.path.join(outputdir, "_tmp_axial_whlcbl_ctx.png")
    tmp_sag = os.path.join(outputdir, "_tmp_sag_whlcbl_ctx.png")
    tmp_cor = os.path.join(outputdir, "_tmp_cor_whlcbl_ctx.png")

    # Generate slices with combined ROI mask
    nilearn.plotting.plot_roi(combined_outline_nii, masked_img, display_mode='z', black_bg=True, alpha=1.0, cmap=combined_cmap, draw_cross=False,
        cut_coords=25, colorbar=False, output_file=tmp_axial)
    nilearn.plotting.plot_roi(combined_outline_nii, masked_img, display_mode='x', black_bg=True, alpha=1.0, cmap=combined_cmap, draw_cross=False,
        cut_coords=[5], colorbar=False, annotate=False, output_file=tmp_sag)
    nilearn.plotting.plot_roi(combined_outline_nii, masked_img, display_mode='y', black_bg=True, alpha=1.0, cmap=combined_cmap, draw_cross=False,
        cut_coords=1, colorbar=False, annotate=False, output_file=tmp_cor)

    # Load images
    img_axial_combined = mpimg.imread(tmp_axial)
    img_sag_combined = crop_black_borders(mpimg.imread(tmp_sag))
    img_cor_combined = crop_black_borders(mpimg.imread(tmp_cor))

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

    # Create combined figure with larger sagittal/coronal views
    fig = plt.figure(figsize=(24, 14), facecolor='black')
    gs = GridSpec(2, 2, figure=fig, width_ratios=[3, 2], hspace=0.02, wspace=0.02)

    ax1 = fig.add_subplot(gs[:, 0])
    ax1.imshow(img_axial_grid)
    ax1.set_facecolor('black')
    ax1.axis('off')
    # Shrink each axes box to its image's aspect ratio so no black padding is
    # added, then anchor: grid to the right edge of the left column ('E'),
    # sagittal/coronal to the left edge of the right column ('W'). This removes
    # the blank space between the axial grid and the sagittal/coronal views.
    ax1.set_box_aspect(img_axial_grid.shape[0] / img_axial_grid.shape[1])
    ax1.set_anchor('E')

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(img_sag_combined)
    ax2.set_facecolor('black')
    ax2.axis('off')
    ax2.set_box_aspect(img_sag_combined.shape[0] / img_sag_combined.shape[1])
    ax2.set_anchor('W')

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.imshow(img_cor_combined)
    ax3.set_facecolor('black')
    ax3.axis('off')
    ax3.set_box_aspect(img_cor_combined.shape[0] / img_cor_combined.shape[1])
    ax3.set_anchor('W')

    combined_path = os.path.join(outputdir, "WhlCbl_ctx_SUVR_combined.png")
    fig.savefig(combined_path, facecolor='black', dpi=150, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    # Clean up temporary files
    os.remove(tmp_axial)
    os.remove(tmp_sag)
    os.remove(tmp_cor)

# Now plot the absolute SUVR with discrete scale for visualization
n_colors = 16
base_cmap = plt.get_cmap('jet')
color_list = base_cmap(np.linspace(0, 1, n_colors))
discrete_cmap = ListedColormap(color_list)

nilearn.plotting.plot_stat_map(masked_img, display_mode='mosaic', bg_img=None, black_bg=True, draw_cross=False, cmap=base_cmap,
        cut_coords=8, title="SUVR_mosaic", cbar_tick_format="%i",vmin=0, vmax=3,
        output_file=os.path.join(outputdir, "SUVR_mosaic.png"))
