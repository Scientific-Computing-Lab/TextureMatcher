# Human study stimuli (version 2)

The 25 image pairs used in the human study, plus the practice pair. All images are 128 x 128 PNG, identical to what participants saw.

## Layout

- `pairs/<pair>_<category A>_<category B>/`: `A.png`, `B.png`, `<representation>_natural.png`, `<representation>_OT.png` (midpoints, t = 0.5). Each pair was shown in one representation.
- `practice/`: the practice pair. Its answers are not recorded.
- `index.csv`: all 400 candidates (pair x representation) with their LPIPS distance and the reason each was kept or removed.

## Selection

Candidates: 120 pairs for CNT, Texture Mixer and DINO-RAE, and 40 pairs for DiffMorpher (the pairs with OT renders), 400 in total.

Selection used only how different the two midpoints are from each other. It did not use which image was OT, which looked better, or any participant response.

1. Remove the practice pair and all pairs with the category "freckled" (face images).
2. Keep candidates whose natural and OT midpoints have LPIPS >= 0.20 (AlexNet, 128 px). The cutoff is the same for all representations and was set from a blind calibration sheet ordered by distance.
3. Draw 25 pairs with a seeded shuffle (`midpoint-human-study-v2`), each pair used once: 8 CNT, 7 Texture Mixer, 7 DINO-RAE, 3 DiffMorpher. DiffMorpher has only a few eligible pairs, so it was filled first.
4. Review the draw visually with the two midpoints in random, unlabeled order. Reject only if the two midpoints look nearly identical or an input is a face. Rejected candidates were replaced from a fixed seeded reserve (`midpoint-human-study-v2-reserve`).

## What the selection means for interpretation

Results describe cases where the two methods produce visibly different midpoints. They are not an estimate over all pairs. There was no upper limit on the distance, so large differences caused by a failure of either method remain in the study.

In DiffMorpher, only 4 of 40 pairs reached the cutoff, because OT attention usually changes the output very little. One of the 4 is a freckled pair, leaving 3.

`index.csv` status values: `in_study`, `eligible_not_drawn`, `too_similar_lpips`, `rejected_visual_near_identical`, `rejected_visual_face`, `excluded_freckled_faces`, `practice_pair`.

## Conditions

| Representation | `_natural` | `_OT` |
|---|---|---|
| CNT | style-map field linear (`cnt_field_linear`) | soft OT (`cnt_soft_ot`) |
| TM (Texture Mixer) | latent lerp (`tmc/lerp`) | OT, r = 0.03 (`tmc/ot_r0.03`) |
| RAE (DINOv2-RAE) | field linear (`rae_field_linear`) | sharp soft OT (`rae_soft_ot_sharp`) |
| DM (DiffMorpher) | official positional attention blend (`diffmorpher`) | two-sided OT attention blend (`dm_ot_twosided`) |

Source folders are in `masters_texture/cvpr_experiments/renders/`, or `masters_texture/tm_scale1000/` for Texture Mixer.
