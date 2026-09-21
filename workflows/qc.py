"""
greedyPOP QC flags.

Signals:
  * Cortical asymmetry index (AI), reported two ways:
      - global, over the Centiloid neocortical VOI (whole-hemisphere balance);
      - per lobe (frontal/parietal/temporal/occipital), from an MNI-space
        label atlas split L/R at the midline -- catches focal/regional
        asymmetry the global VOI averages out.
      AI = 100 * (L - R) / ((L + R)/2). Reference-invariant (the reference
      cancels), so it is unaffected by which reference region is used.
  * Whole-cerebellum / cerebellar-gray uptake ratio, a single reference-region
      anomaly flag (moves under WM contamination -> CL underestimate, or under
      cerebellar atrophy/CSF partial volume -> CL overestimate). Raw WhlCbl and
      CerebGry means are reported so a human can read the direction.
  * Dice: the effective registration Dice, printed for interpretation only.

"""

import os
import numpy as np
import nibabel as nb
import pandas as pd
from datetime import datetime

# ----------------------------------------------------------------------------
# Tunable thresholds  (PLACEHOLDERS -- set from your own clean scans)
# ----------------------------------------------------------------------------

# Flag if |AI| exceeds this (percent), applied to the global VOI and per lobe.
ASYM_AI_ABS_PCT = 10.0

# Flag if WhlCbl/CerebGry falls outside this band (see module docstring).
CBL_GRY_RATIO_LOW = 1.05
CBL_GRY_RATIO_HIGH = 1.35

# MNI structural atlas (FSL MNI-maxprob-thr25-2mm) cortical-lobe label values.
# FSL stores voxel value = MNI.xml label index + 1. VERIFY against the MNI.xml
# shipped with your atlas file; a wrong number here would measure the wrong
# region (the code errors loudly if a label is missing, but not if it's swapped).
MNI_LOBE_LABELS = {
    'Frontal':   3,
    'Parietal':  6,
    'Temporal':  8,
    'Occipital': 5,
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _split_lr(mask_img):
    """Split a binary mask into (left_img, right_img) at its own centroid along
    the L/R axis, for the single bilateral Centiloid ctx VOI."""
    data = np.asarray(mask_img.dataobj) > 0
    axcodes = nb.aff2axcodes(mask_img.affine)
    lr_axis = next(i for i, c in enumerate(axcodes) if c in ('L', 'R'))
    code = axcodes[lr_axis]

    idx = np.where(data)
    if idx[lr_axis].size == 0:
        raise ValueError("Cortical VOI mask is empty -- cannot compute asymmetry.")
    centroid = idx[lr_axis].mean()

    shape = [1, 1, 1]
    shape[lr_axis] = -1
    coord = np.arange(data.shape[lr_axis]).reshape(shape)

    low = data & (coord < centroid)
    high = data & (coord >= centroid)
    if code == 'R':
        right, left = high, low
    else:
        right, left = low, high

    left_img = nb.Nifti1Image(left.astype(np.uint8), mask_img.affine, mask_img.header)
    right_img = nb.Nifti1Image(right.astype(np.uint8), mask_img.affine, mask_img.header)
    return left_img, right_img


def _world_x(shape, affine):
    """World (RAS+) x coordinate of every voxel, for midline (x=0) splitting.
    +x = Right, -x = Left."""
    i, j, k = np.indices(shape)
    return affine[0, 0] * i + affine[0, 1] * j + affine[0, 2] * k + affine[0, 3]


def _lobar_asymmetry(smoothed_img, atlas_path):
    """Per-lobe L/R asymmetry from an MNI-space label atlas. Returns
    (results_dict, warnings_list). Atlas is resampled onto the PET grid with
    nearest-neighbour interpolation (both are MNI152, so this is a grid change,
    not a registration)."""
    from nilearn.image import resample_to_img
    atlas_img = nb.load(atlas_path)
    atlas_r = resample_to_img(atlas_img, smoothed_img, interpolation='nearest')
    atlas = np.rint(np.asarray(atlas_r.dataobj)).astype(int)
    pet = np.asarray(smoothed_img.dataobj, dtype=float)

    world_x = _world_x(atlas.shape, smoothed_img.affine)
    is_left = world_x < 0
    is_right = world_x > 0

    results, warns = {}, []
    present = set(np.unique(atlas).tolist())
    for name, lab in MNI_LOBE_LABELS.items():
        if lab not in present:
            warns.append(f"lobe label {lab} ({name}) not in atlas -- check MNI_LOBE_LABELS.")
            continue
        lobe = atlas == lab
        lmask, rmask = lobe & is_left, lobe & is_right
        if lmask.sum() == 0 or rmask.sum() == 0:
            warns.append(f"{name}: empty L or R side after midline split -- skipped.")
            continue
        mL, mR = float(pet[lmask].mean()), float(pet[rmask].mean())
        denom = (mL + mR) / 2.0
        ai = float(100.0 * (mL - mR) / denom) if denom else float('nan')
        results[name] = {'mean_L': mL, 'mean_R': mR, 'AI_pct': ai}
    return results, warns


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------

def compute_qc_flags(smoothed_img, ctx_resamp, masked_mean_from_disk,
                     avg_wc_voi_bin, avg_wcgm_voi_bin, effective_dice,
                     output_dir, atlas_path=None, subject_id="sw_pet.nii.gz"):
    """Compute QC metrics, write a separate QC CSV, print headline values, and
    return a list of warning strings (empty if nothing tripped)."""

    # --- Global cortical asymmetry over the Centiloid VOI ---
    left_img, right_img = _split_lr(ctx_resamp)
    mean_L = masked_mean_from_disk(smoothed_img, left_img)
    mean_R = masked_mean_from_disk(smoothed_img, right_img)
    denom = (mean_L + mean_R) / 2.0
    asym_ai_pct = float(100.0 * (mean_L - mean_R) / denom) if denom else np.nan
    suvr_L = float(mean_L / avg_wc_voi_bin) if avg_wc_voi_bin else np.nan
    suvr_R = float(mean_R / avg_wc_voi_bin) if avg_wc_voi_bin else np.nan
    global_flag = bool(np.isfinite(asym_ai_pct) and abs(asym_ai_pct) > ASYM_AI_ABS_PCT)

    # --- Per-lobe asymmetry from the MNI atlas ---
    lobar, lobar_notes = {}, []
    if atlas_path and os.path.exists(atlas_path):
        try:
            lobar, lobar_notes = _lobar_asymmetry(smoothed_img, atlas_path)
        except Exception as e:
            lobar_notes = [f"lobar asymmetry could not be computed: {e}"]
    else:
        lobar_notes = ["lobar atlas not found; per-lobe asymmetry skipped."]

    lobar_ai = {n: v['AI_pct'] for n, v in lobar.items() if np.isfinite(v['AI_pct'])}
    if lobar_ai:
        max_lobe = max(lobar_ai, key=lambda n: abs(lobar_ai[n]))
        max_lobar_ai = lobar_ai[max_lobe]
    else:
        max_lobe, max_lobar_ai = None, np.nan
    lobar_flag = any(abs(a) > ASYM_AI_ABS_PCT for a in lobar_ai.values())

    asym_flag = bool(global_flag or lobar_flag)

    # --- Cerebellar reference anomaly (both directions) ---
    ratio = float(avg_wc_voi_bin / avg_wcgm_voi_bin) if avg_wcgm_voi_bin else np.nan
    ratio_flag = bool(np.isfinite(ratio) and
                      (ratio < CBL_GRY_RATIO_LOW or ratio > CBL_GRY_RATIO_HIGH))

    qc = {
        'subjectID': [subject_id],
        'Dice_effective': [float(effective_dice)],
        # global asymmetry
        'ctx_mean_L': [float(mean_L)],
        'ctx_mean_R': [float(mean_R)],
        'ctx_SUVR_L_WhlCbl': [suvr_L],
        'ctx_SUVR_R_WhlCbl': [suvr_R],
        'global_AI_pct': [asym_ai_pct],
        'global_AI_flag': [global_flag],
        # lobar asymmetry
        'max_lobar_AI_pct': [max_lobar_ai],
        'max_lobar_region': [max_lobe if max_lobe else ''],
        'lobar_AI_flag': [lobar_flag],
        'Asymmetry_flag': [asym_flag],
        'Asymmetry_threshold_pct': [ASYM_AI_ABS_PCT],
        # cerebellar reference
        'avg_WhlCbl': [float(avg_wc_voi_bin)],
        'avg_CerebGry': [float(avg_wcgm_voi_bin)],
        'WhlCbl_to_CerebGry_ratio': [ratio],
        'RefAnomaly_flag': [ratio_flag],
        'WhlCbl_CerebGry_band_low': [CBL_GRY_RATIO_LOW],
        'WhlCbl_CerebGry_band_high': [CBL_GRY_RATIO_HIGH],
    }
    # per-lobe columns
    for name in MNI_LOBE_LABELS:
        v = lobar.get(name)
        qc[f'{name}_AI_pct'] = [v['AI_pct'] if v else np.nan]
        qc[f'{name}_mean_L'] = [v['mean_L'] if v else np.nan]
        qc[f'{name}_mean_R'] = [v['mean_R'] if v else np.nan]

    ts = datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    qc_file = os.path.join(output_dir, f'greedyPOP_QC_{ts}.csv')
    pd.DataFrame(qc).to_csv(qc_file, index=False)

    print(f"\nQC metrics written to {qc_file}")
    print(f"  Dice (effective registration): {float(effective_dice):.2f}")
    print(f"  Global cortical AI: {asym_ai_pct:.2f}%  (flag={global_flag})")
    if lobar_ai:
        print("  Lobar AI: " + ", ".join(f"{n} {a:+.1f}%" for n, a in lobar_ai.items()))
    for note in lobar_notes:
        print(f"  [lobar] {note}")
    print(f"  WhlCbl/CerebGry ratio: {ratio:.3f}  (flag={ratio_flag})")

    warnings = []
    if global_flag:
        warnings.append(f"Global cortical asymmetry |AI| = {abs(asym_ai_pct):.1f}% "
                        f"exceeds {ASYM_AI_ABS_PCT:.1f}%.")
    for name, a in lobar_ai.items():
        if abs(a) > ASYM_AI_ABS_PCT:
            side = "L>R" if a > 0 else "R>L"
            warnings.append(f"{name} lobe asymmetry AI = {a:+.1f}% ({side}) "
                            f"exceeds {ASYM_AI_ABS_PCT:.1f}%.")
    if ratio_flag:
        warnings.append(f"WhlCbl/CerebGry ratio = {ratio:.3f} is outside "
                        f"[{CBL_GRY_RATIO_LOW}, {CBL_GRY_RATIO_HIGH}] -- possible "
                        f"reference-region problem; inspect avg_WhlCbl "
                        f"({avg_wc_voi_bin:.3f}) vs avg_CerebGry ({avg_wcgm_voi_bin:.3f}).")
    return warnings
