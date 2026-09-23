# CHECK.md -- score_only.py macro reproduction report

Data root: `(outside the repro package; path omitted for anonymity -- see --data-root/--paper-root)`

Paper root: `paper`


**254 rows checked. 245 MATCH, 0 MISMATCH, 3 have no per-pair file row (see notes per row), 0 have no corresponding paper macro, 6 informational.**

Tolerance: |diff| <= max(0.0006, 2% relative) for plain values (0.0006 covers the
trace-vs-len KID reference-term offset of ~0.000245); wider tolerances are used
explicitly for bootstrap CIs and derived percentages, and are noted per row where
they differ from the default.

## All checks, by table

### Table1-CNT-1000 (38 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `KIDPixel` | 0.03 | 0.030036 | +3.60172e-05 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDPixel` | 108 | 107.957 | -0.0432158 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncPixel` | 0.925 | 0.925042 | +4.203e-05 | MATCH | matching_ablation/final128_n1000.csv |
| `PlacePixel` | 0.048 | 0.048337 | +0.000336975 | MATCH | matching_ablation/final128_n1000.csv |
| `DINOPixel` | 0.858 | 0.857881 | -0.00011942 | MATCH | matching_ablation/final128_n1000.csv |
| `KIDPosition` | 0.047 | 0.0465195 | -0.000480455 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDPosition` | 133.6 | 133.63 | +0.0296761 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncPosition` | 0.894 | 0.894233 | +0.000233385 | MATCH | matching_ablation/final128_n1000.csv |
| `PlacePosition` | 0.038 | 0.038251 | +0.000250965 | MATCH | matching_ablation/final128_n1000.csv |
| `DINOPosition` | 0.843 | 0.843462 | +0.000461845 | MATCH | matching_ablation/final128_n1000.csv |
| `KIDGaussian` | 0.024 | 0.0242456 | +0.000245638 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDGaussian` | 97.9 | 97.9242 | +0.0241765 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncGaussian` | 0.926 | nan | +nan | NO FILE ROW | matching_ablation/final128_n1000.csv |
| `PlaceGaussian` | 0.105 | nan | +nan | NO FILE ROW | matching_ablation/final128_n1000.csv |
| `DINOGaussian` | 0.855 | nan | +nan | NO FILE ROW | matching_ablation/final128_n1000.csv |
| `KIDTransport` | 0.021 | 0.0212789 | +0.000278944 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDTransport` | 94.7 | 94.6735 | -0.026467 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncTransport` | 0.942 | 0.94231 | +0.00030957 | MATCH | matching_ablation/final128_n1000.csv |
| `PlaceTransport` | 0.081 | 0.0809456 | -5.4405e-05 | MATCH | matching_ablation/final128_n1000.csv |
| `DINOTransport` | 0.854 | 0.853579 | -0.000420825 | MATCH | matching_ablation/final128_n1000.csv |
| `KIDHard` | 0.033 | 0.0327225 | -0.000277503 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDHard` | 112.8 | 112.76 | -0.0404103 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncHard` | 0.951 | 0.951249 | +0.00024945 | MATCH | matching_ablation/final128_n1000.csv |
| `PlaceHard` | 0.044 | 0.0436618 | -0.000338215 | MATCH | matching_ablation/final128_n1000.csv |
| `DINOHard` | 0.864 | 0.86365 | -0.00034988 | MATCH | matching_ablation/final128_n1000.csv |
| `KIDSymmetric` | 0.029 | 0.0284578 | -0.000542217 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDSymmetric` | 109 | 108.988 | -0.0116759 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncSymmetric` | 0.961 | 0.961288 | +0.000288455 | MATCH | matching_ablation/final128_n1000.csv |
| `PlaceSymmetric` | 0.047 | 0.0468345 | -0.00016547 | MATCH | matching_ablation/final128_n1000.csv |
| `DINOSymmetric` | 0.868 | 0.868064 | +6.353e-05 | MATCH | matching_ablation/final128_n1000.csv |
| `KIDMixer` | 0.012 | 0.012177 | +0.000177021 | MATCH | matching_ablation/final128_n1000.csv (+recompute, subsampled KID) |
| `FIDMixer` | 82.5 | 82.4921 | -0.00789394 | MATCH | matching_ablation/final128_n1000.csv (+recompute) |
| `IncMixer` | 0.948 | 0.947673 | -0.00032665 | MATCH | matching_ablation/final128_n1000.csv |
| `PlaceMixer` | 0.059 | 0.0592184 | +0.00021844 | MATCH | matching_ablation/final128_n1000.csv |
| `DINOMixer` | 0.907 | 0.907271 | +0.00027098 | MATCH | matching_ablation/final128_n1000.csv |
| `CKIDpctGauss` | 20 | 20 | -3.55271e-15 | MATCH | derived from KIDPixel/KIDGaussian |
| `CKIDpctOT` | 30 | 30 | -7.10543e-15 | MATCH | derived from KIDPixel/KIDTransport |
| `CKIDpctExact` | -10 | -10 | -8.88178e-15 | MATCH | derived from KIDPixel/KIDHard |

### Table-generative-120 (5 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `GFIDotsym` | 208.5 | 208.502 | +0.00191471 | MATCH | feat_ot_sym_inc.npy[k in pairs_120] (+recompute) |
| `GKIDotsym` | 0.0273 | 0.0274267 | +0.000126726 | MATCH | feat_ot_sym_inc.npy[k in pairs_120] (+recompute) |
| `GRIncotsym` | 0.957 | 0.956776 | -0.000223735 | MATCH | final128_n1000.csv[k in pairs_120] |
| `GRDinotsym` | 0.864 | 0.863946 | -5.35e-05 | MATCH | final128_n1000.csv[k in pairs_120] |
| `GPlaceotsym` | 0.044 | 0.043609 | -0.00039102 | MATCH | final128_n1000.csv[k in pairs_120] |

### Table1-TM-1000 (20 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `TMkKIDlerp` | 0.0121 | 0.0121132 | +1.31937e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkRInclerp` | 0.948 | 0.947995 | -5.41019e-06 | MATCH | jackknife/scores_tm1000_*.csv |
| `TMkBallerp` | 0.056 | 0.0563528 | +0.000352821 | MATCH | jackknife/scores_tm1000_*.csv |
| `TMkKIDmean` | 0.009 | 0.00899753 | -2.47473e-06 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkRIncmean` | 0.97 | 0.970208 | +0.000208317 | MATCH | jackknife/scores_tm1000_*.csv |
| `TMkBalmean` | 0.077 | 0.0772043 | +0.000204314 | MATCH | jackknife/scores_tm1000_*.csv |
| `TMkKIDot` | 0.0093 | 0.00928261 | -1.73918e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkRIncot` | 0.955 | 0.95501 | +9.84788e-06 | MATCH | jackknife/scores_tm1000_*.csv |
| `TMkBalot` | 0.078 | 0.0775149 | -0.000485133 | MATCH | jackknife/scores_tm1000_*.csv |
| `TMkdKIDmean` | -0.0031 | -0.00311567 | -1.56684e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDmeanCI.lo` | -0.0044 | -0.00443738 | -3.73769e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDmeanCI.hi` | -0.0018 | -0.00179396 | +6.03998e-06 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDot` | -0.0028 | -0.00283059 | -3.05855e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDotCI.lo` | -0.0039 | -0.00394601 | -4.60143e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDotCI.hi` | -0.0017 | -0.00171516 | -1.51566e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDotVsMean` | 0.0003 | 0.000285083 | -1.4917e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDotVsMeanCI.lo` | -0.0006 | -0.000623271 | -2.32712e-05 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkdKIDotVsMeanCI.hi` | 0.0012 | 0.00119344 | -6.5629e-06 | MATCH | jackknife/feats_tm1000_*.npy (+recompute) |
| `TMkKIDgain` | 26 | 25.7213 | -0.27872 | MATCH | derived (mean vs lerp) |
| `TMkKIDpctOT` | 23 | 23.3678 | +0.367788 | MATCH | derived (ot vs lerp) |

### tab:eqsample (45 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `EqKIDlinear` | 0.0322 | 0.0322252 | +2.5219e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqFIDlinear` | 189.3 | 189.269 | -0.0306792 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqBallinear` | 0.046 | 0.0462006 | +0.000200649 | MATCH | jackknife/scores_eq_*.csv |
| `EqRInclinear` | 0.923 | 0.922667 | -0.000333391 | MATCH | jackknife/scores_eq_*.csv |
| `EqKIDhard` | 0.03 | 0.0300202 | +2.01542e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqFIDhard` | 183.4 | 183.356 | -0.0435518 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqBalhard` | 0.043 | 0.042685 | -0.000315039 | MATCH | jackknife/scores_eq_*.csv |
| `EqRInchard` | 0.952 | 0.951918 | -8.16066e-05 | MATCH | jackknife/scores_eq_*.csv |
| `EqKIDotSharp` | 0.0197 | 0.0197482 | +4.81925e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqFIDotSharp` | 174.5 | 174.55 | +0.0497156 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqBalotSharp` | 0.067 | 0.0668323 | -0.000167655 | MATCH | jackknife/scores_eq_*.csv |
| `EqRIncotSharp` | 0.933 | 0.933238 | +0.000238268 | MATCH | jackknife/scores_eq_*.csv |
| `EqKIDot` | 0.0216 | 0.0215678 | -3.21687e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqFIDot` | 177.6 | 177.568 | -0.0324983 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqBalot` | 0.072 | 0.0715746 | -0.000425379 | MATCH | jackknife/scores_eq_*.csv |
| `EqRIncot` | 0.931 | 0.930959 | -4.06859e-05 | MATCH | jackknife/scores_eq_*.csv |
| `EqKIDpaper` | 0.0198 | 0.0198475 | +4.74749e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqFIDpaper` | 174.9 | 174.902 | +0.0016723 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqGaphard` | 0.81 | 0.809843 | -0.000156668 | MATCH | evidence/eqsample_summary.csv |
| `EqGapotSharp` | 0.84 | 0.839269 | -0.000731047 | MATCH | evidence/eqsample_summary.csv |
| `EqGapot` | 0.87 | 0.86833 | -0.00167012 | MATCH | evidence/eqsample_summary.csv |
| `EqVarRetSharp` | 0.88 | 0.879566 | -0.000433806 | MATCH | evidence/eqsample_summary.csv |
| `EqVarRet` | 0.38 | 0.37988 | -0.000119585 | MATCH | evidence/eqsample_summary.csv |
| `EqdKIDotVsLinear` | -0.0107 | -0.0106574 | +4.26122e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDotVsLinearCI.lo` | -0.0154 | -0.0154338 | -3.38216e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDotVsLinearCI.hi` | -0.0059 | -0.00588095 | +1.90461e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDotPaperVsLinear` | -0.0124 | -0.0123777 | +2.22558e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDotPaperVsLinearCI.lo` | -0.0172 | -0.0171927 | +7.28935e-06 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDotPaperVsLinearCI.hi` | -0.0076 | -0.00756278 | +3.72223e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardVsLinear` | -0.0022 | -0.00220506 | -5.06482e-06 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardVsLinearCI.lo` | -0.0066 | -0.0066094 | -9.39556e-06 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardVsLinearCI.hi` | 0.0022 | 0.00219927 | -7.34074e-07 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhard` | 0.0085 | 0.00845232 | -4.76771e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardCI.lo` | 0.0049 | 0.00488489 | -1.51112e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardCI.hi` | 0.012 | 0.0120198 | +1.97571e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardSharp` | 0.0103 | 0.010272 | -2.80383e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardSharpCI.lo` | 0.007 | 0.00703964 | +3.96385e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDhardSharpCI.hi` | 0.0135 | 0.0135043 | +4.28489e-06 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDsharp` | -0.0018 | -0.00181964 | -1.96388e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDsharpCI.lo` | -0.0035 | -0.00349819 | +1.8092e-06 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqdKIDsharpCI.hi` | -0.0001 | -0.000141087 | -4.10867e-05 | MATCH | jackknife/feats_eq_*.npy (+recompute) |
| `EqKIDgainOT` | 38 | 38.4101 | +0.410116 | MATCH | derived (paper vs linear) |
| `EqFIDgainOT` | 8 | 7.59111 | -0.408887 | MATCH | derived (paper vs linear) |
| `EqKIDgainOTsmall` | 33 | 33.0716 | +0.0715758 | MATCH | derived (4096-sample ot_e0.05 vs linear) |
| `EqBalP (actual p)` | 10 | 1.7201e-14 | +nan | SEE NOTE: paper says p<value, actual p=1.72e-14 | jackknife/scores_eq_{hard,ot_e0.05}.csv (+recompute, paired Wilcoxon) |

### tab:generative-120 (77 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `GKIDpix` | 0.0305 | 0.0304551 | -4.49053e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDpix` | 218.9 | 218.873 | -0.0271149 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRIncpix` | 0.913 | 0.913093 | +9.29708e-05 | MATCH | jackknife/scores_g_*.csv |
| `GRDinpix` | 0.856 | 0.856252 | +0.000252402 | MATCH | jackknife/scores_g_*.csv |
| `GPlacepix` | 0.041 | 0.0410594 | +5.93636e-05 | MATCH | jackknife/scores_g_*.csv |
| `GKIDtex` | 0.0504 | 0.0503643 | -3.56547e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDtex` | 247.9 | 247.928 | +0.0283163 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRInctex` | 0.897 | 0.896979 | -2.13535e-05 | MATCH | jackknife/scores_g_*.csv |
| `GRDintex` | 0.849 | 0.849333 | +0.000333137 | MATCH | jackknife/scores_g_*.csv |
| `GPlacetex` | 0.04 | 0.0400823 | +8.23207e-05 | MATCH | jackknife/scores_g_*.csv |
| `GKIDgauss` | 0.0253 | 0.0252932 | -6.84191e-06 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDgauss` | 216.2 | 216.202 | +0.00162077 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRIncgauss` | 0.919 | 0.919091 | +9.11055e-05 | MATCH | jackknife/scores_g_*.csv |
| `GRDingauss` | 0.847 | 0.847479 | +0.000479075 | MATCH | jackknife/scores_g_*.csv |
| `GPlacegauss` | 0.103 | 0.102913 | -8.73999e-05 | MATCH | jackknife/scores_g_*.csv |
| `GKIDot` | 0.019 | 0.0190349 | +3.49302e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDot` | 208.2 | 208.196 | -0.00408703 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRIncot` | 0.924 | 0.924314 | +0.000314052 | MATCH | jackknife/scores_g_*.csv |
| `GRDinot` | 0.851 | 0.850577 | -0.000422795 | MATCH | jackknife/scores_g_*.csv |
| `GPlaceot` | 0.081 | 0.0808902 | -0.000109788 | MATCH | jackknife/scores_g_*.csv |
| `GKIDhard` | 0.0302 | 0.0301916 | -8.38284e-06 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDhard` | 211.8 | 211.82 | +0.0200444 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRInchard` | 0.943 | 0.94282 | -0.000179987 | MATCH | jackknife/scores_g_*.csv |
| `GRDinhard` | 0.871 | 0.870601 | -0.000398584 | MATCH | jackknife/scores_g_*.csv |
| `GPlacehard` | 0.044 | 0.043522 | -0.000477957 | MATCH | jackknife/scores_g_*.csv |
| `GKIDtm` | 0.0119 | 0.0119418 | +4.18036e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDtm` | 204 | 203.998 | -0.00178772 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRInctm` | 0.948 | 0.948264 | +0.000263884 | MATCH | jackknife/scores_g_*.csv |
| `GRDintm` | 0.907 | 0.907143 | +0.000143295 | MATCH | jackknife/scores_g_*.csv |
| `GPlacetm` | 0.061 | 0.0605213 | -0.000478715 | MATCH | jackknife/scores_g_*.csv |
| `GKIDgpt` | 0.0051 | 0.0050743 | -2.57007e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDgpt` | 193.7 | 193.701 | +0.00100405 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRIncgpt` | 0.96 | 0.959621 | -0.000378571 | MATCH | jackknife/scores_g_*.csv |
| `GRDingpt` | 0.906 | 0.905574 | -0.000425678 | MATCH | jackknife/scores_g_*.csv |
| `GPlacegpt` | 0.054 | 0.0537889 | -0.000211104 | MATCH | jackknife/scores_g_*.csv |
| `GKIDgptsym` | 0.0087 | 0.00871663 | +1.66295e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GFIDgptsym` | 201.1 | 201.064 | -0.0360014 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GRIncgptsym` | 0.953 | 0.953434 | +0.000433871 | MATCH | jackknife/scores_g_*.csv |
| `GRDingptsym` | 0.969 | 0.969446 | +0.000445527 | MATCH | jackknife/scores_g_*.csv |
| `GPlacegptsym` | 0.046 | 0.046377 | +0.000376996 | MATCH | jackknife/scores_g_*.csv |
| `TMKIDlerp` | 0.0119 | 0.0119145 | +1.45237e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMFIDlerp` | 203.9 | 203.944 | +0.044324 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMRInclerp` | 0.949 | 0.948981 | -1.90427e-05 | MATCH | jackknife/scores_g_*.csv |
| `TMRDinlerp` | 0.909 | 0.908714 | -0.000285735 | MATCH | jackknife/scores_g_*.csv |
| `TMBallerp` | 0.06 | 0.0603023 | +0.000302296 | MATCH | jackknife/scores_g_*.csv |
| `TMKIDmean` | 0.0084 | 0.0084151 | +1.51021e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMFIDmean` | 201.2 | 201.194 | -0.00559251 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMRIncmean` | 0.957 | 0.957002 | +1.98412e-06 | MATCH | jackknife/scores_g_*.csv |
| `TMRDinmean` | 0.923 | 0.922886 | -0.000114403 | MATCH | jackknife/scores_g_*.csv |
| `TMBalmean` | 0.077 | 0.0772595 | +0.000259525 | MATCH | jackknife/scores_g_*.csv |
| `TMKIDot` | 0.0099 | 0.00989023 | -9.7654e-06 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMFIDot` | 204 | 204.008 | +0.00801889 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMRIncot` | 0.942 | 0.942354 | +0.000354292 | MATCH | jackknife/scores_g_*.csv |
| `TMRDinot` | 0.922 | 0.922051 | +5.13701e-05 | MATCH | jackknife/scores_g_*.csv |
| `TMBalot` | 0.072 | 0.0721442 | +0.000144249 | MATCH | jackknife/scores_g_*.csv |
| `TMKIDhard` | 0.0206 | 0.0206124 | +1.23715e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMFIDhard` | 215.1 | 215.14 | +0.0404407 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMRInchard` | 0.966 | 0.965961 | -3.89311e-05 | MATCH | jackknife/scores_g_*.csv |
| `TMRDinhard` | 0.922 | 0.921915 | -8.53629e-05 | MATCH | jackknife/scores_g_*.csv |
| `TMBalhard` | 0.052 | 0.052195 | +0.000195014 | MATCH | jackknife/scores_g_*.csv |
| `GdKIDotVsPix` | -0.0114 | -0.0114202 | -2.01645e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GdKIDotVsPixCI.lo` | -0.0174 | -0.0174372 | -3.71954e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `GdKIDotVsPixCI.hi` | -0.0054 | -0.00540313 | -3.13356e-06 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDmean` | -0.0035 | -0.00349942 | +5.78349e-07 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDmeanCI.lo` | -0.0074 | -0.00741459 | -1.45898e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDmeanCI.hi` | 0.0004 | 0.000415747 | +1.57465e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDot` | -0.002 | -0.00202429 | -2.42891e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDotCI.lo` | -0.006 | -0.00604901 | -4.90094e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDotCI.hi` | 0.002 | 0.00200043 | +4.31193e-07 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDhard` | 0.0087 | 0.00869785 | -2.15225e-06 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDhardCI.lo` | 0.0042 | 0.00415465 | -4.53475e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDhardCI.hi` | 0.0132 | 0.013241 | +4.1043e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDotVsMean` | 0.0015 | 0.00147513 | -2.48675e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDotVsMeanCI.lo` | -0.0016 | -0.00155871 | +4.12875e-05 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMdKIDotVsMeanCI.hi` | 0.0045 | 0.00450898 | +8.9776e-06 | MATCH | jackknife/feats_g_*.npy (+recompute) |
| `TMKIDgainMean` | 29 | 29.3711 | +0.371058 | MATCH | derived |
| `TMKIDgainOT` | 17 | 16.9901 | -0.00990316 | MATCH | derived |

### tab:rules-200 (32 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `RuleKIDRandom` | 0.077 | 0.0767987 | -0.000201341 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDRandom` | 224.3 | 224.303 | +0.00301795 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDMean` | 0.025 | 0.0253349 | +0.00033492 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDMean` | 183.7 | 183.658 | -0.0422586 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDPixel` | 0.031 | 0.0310891 | +8.90511e-05 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDPixel` | 188.7 | 188.685 | -0.0145198 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDPosition` | 0.043 | 0.0427639 | -0.000236063 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDPosition` | 211.8 | 211.814 | +0.0141157 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDGaussian` | 0.022 | 0.0215473 | -0.000452691 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDGaussian` | 177.6 | 177.608 | +0.00787862 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDNN` | 0.027 | 0.0271125 | +0.000112462 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDNN` | 182.4 | 182.441 | +0.0407028 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDHard` | 0.031 | 0.0304927 | -0.000507305 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDHard` | 184.2 | 184.155 | -0.0451559 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDTransport` | 0.02 | 0.0198274 | -0.000172558 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDTransport` | 174.9 | 174.85 | -0.0496598 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RuleKIDSharp` | 0.019 | 0.0191004 | +0.000100433 | MATCH | matching_ablation/rules_feats.npz (+recompute, subsampled KID) |
| `RuleFIDSharp` | 173.7 | 173.691 | -0.00871096 | MATCH | matching_ablation/rules_feats.npz (+recompute) |
| `RandomIncRealism` | 1.035 | 1.03515 | +0.000148323 | MATCH | matching_ablation/rules_n200.csv |
| `RandomDINORealism` | 0.926 | 0.92593 | -7.03344e-05 | MATCH | matching_ablation/rules_n200.csv |
| `(inline) NN balance` | nan | 0.0463199 | +nan | INFO (b=0.046, gap=0.810; see supplement.tex prose) | matching_ablation/rules_n200.csv |
| `(inline) Hard/Exact balance` | nan | 0.0432797 | +nan | INFO (b=0.043, gap=0.808; see supplement.tex prose) | matching_ablation/rules_n200.csv |
| `(inline) Soft-OT balance` | nan | 0.081266 | +nan | INFO (b=0.081, gap=0.868; see supplement.tex prose) | matching_ablation/rules_n200.csv |
| `MeanRealismDelta` | -0.016 | -0.015749 | +0.000250993 | MATCH | matching_ablation/rules_n200.csv (+recompute, paired median) |
| `MeanRealismDeltaCI.lo` | -0.029 | -0.028578 | +0.000422017 | MATCH | matching_ablation/rules_n200.csv (+bootstrap, seed varies) |
| `MeanRealismDeltaCI.hi` | -0.003 | -0.00315326 | -0.000153265 | MATCH | matching_ablation/rules_n200.csv (+bootstrap, seed varies) |
| `RandomRealismDelta` | 0.095 | 0.0949087 | -9.12857e-05 | MATCH | matching_ablation/rules_n200.csv (+recompute, paired median) |
| `RandomRealismDeltaCI.lo` | 0.076 | 0.0755804 | -0.000419561 | MATCH | matching_ablation/rules_n200.csv (+bootstrap, seed varies) |
| `RandomRealismDeltaCI.hi` | 0.114 | 0.113575 | -0.000424711 | MATCH | matching_ablation/rules_n200.csv (+bootstrap, seed varies) |
| `HardRealismDelta` | 0.02 | 0.020409 | +0.000408958 | MATCH | matching_ablation/rules_n200.csv (+recompute, paired median) |
| `HardRealismDeltaCI.lo` | -0.007 | -0.00680725 | +0.00019275 | MATCH | matching_ablation/rules_n200.csv (+bootstrap, seed varies) |
| `HardRealismDeltaCI.hi` | 0.037 | 0.0371695 | +0.000169486 | MATCH | matching_ablation/rules_n200.csv (+bootstrap, seed varies) |

### tab:app-primitives-120 (14 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `GEKIDmorphP` | 0.036 | 0.0363785 | +0.000378528 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEKIDmorphA` | 0.08 | 0.0796996 | -0.000300431 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEKIDfixP` | 0.03 | 0.0299778 | -2.2238e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEKIDfixA` | 0.03 | 0.0300921 | +9.20507e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEKIDfixPA` | 0.027 | 0.0266743 | -0.000325711 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEdKIDmorph` | 0.0433 | 0.043321 | +2.10406e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEdKIDmorphCI.lo` | 0.0333 | 0.0332658 | -3.41815e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEdKIDmorphCI.hi` | 0.0534 | 0.0533763 | -2.37373e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEdKIDfix` | 0.0001 | 0.000114289 | +1.42886e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEdKIDfixCI.lo` | -0.0041 | -0.00409914 | +8.5665e-07 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEdKIDfixCI.hi` | 0.0043 | 0.00432772 | +2.77206e-05 | MATCH | correspondence/feats/E1.npz (+recompute) |
| `GEKIDprimSoft` | 0.016 | 0.0159328 | -6.7247e-05 | MATCH | correspondence/feats/E4.npz (+recompute) |
| `GEKIDdenseOT` | 0.019 | 0.0190349 | +3.49302e-05 | MATCH | correspondence/feats/E4.npz (+recompute) |
| `GEKIDprimHard` | 0.03 | 0.0299778 | -2.2238e-05 | MATCH | correspondence/feats/E1.npz (+recompute, one-to-one position row) |

### app:ceiling-120 (9 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `CeilKIDorig` | 0.009 | 0.00902775 | +2.77491e-05 | MATCH | joint_basis/feats_ceiling.npz vs ref_inc_win128.npy (+recompute) |
| `CeilKIDrec` | 0.014 | 0.0139209 | -7.90906e-05 | MATCH | joint_basis/feats_ceiling.npz vs ref_inc_win128.npy (+recompute) |
| `CeilKIDrecTwo` | 0.025 | 0.0243872 | -0.00061277 | MATCH | joint_basis/feats_ceiling.npz vs ref_inc_win128.npy (+recompute) |
| `CeilKIDmid` | 0.023 | 0.0231215 | +0.00012155 | MATCH | jackknife/feats_g_ot.npy vs joint_basis/ref_inc_win128.npy (+recompute) |
| `CeilLPIPSrec` | 0.21 | 0.205813 | -0.00418729 | MATCH | joint_basis/ceiling.csv |
| `CeilRealOrig` | 1 | 0.996574 | -0.00342642 | MATCH | joint_basis/ceiling_summary.json:decomposition.orig |
| `CeilRealRec` | 0.9 | 0.904028 | +0.00402819 | MATCH | joint_basis/ceiling_summary.json:decomposition.rec1 |
| `CeilRealMid` | 0.85 | 0.850577 | +0.000577265 | MATCH | joint_basis/ceiling_summary.json:decomposition.mid |
| `CeilRho` | 0.08 | 0.0829295 | +0.00292951 | MATCH | joint_basis/ceiling_summary.json:spearman.rho_mid (file value; recompute needs a per-pair reconstruction-error join, not attempted) |

### fig:app-alignshift (8 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `AlignN` | 40 | 40 | +0 | MATCH | evidence/alignment_scores.csv |
| `AlignLinZero` | 0 | 0 | +0 | MATCH | evidence/alignment_scores.csv (+recompute, median dino_dev @t=0.5) |
| `AlignLinSixteen` | 15.2 | 15.1591 | -0.0408723 | MATCH | evidence/alignment_scores.csv (+recompute, median dino_dev @t=0.5) |
| `AlignLinMax` | 23.9 | 23.9465 | +0.0465389 | MATCH | evidence/alignment_scores.csv (+recompute, median dino_dev @t=0.5) |
| `AlignGaussDev` | 18.2 | 18.2007 | +0.000697422 | MATCH | evidence/alignment_scores.csv (+recompute, mean of per-shift medians @t=0.5) |
| `AlignOTdev` | 22.4 | 22.3161 | -0.0838517 | MATCH | evidence/alignment_scores.csv (+recompute, mean of per-shift medians @t=0.5) |
| `AlignCrossLo` | 16 | 16 | +nan | INFO (literal shift label, not a computed value) | evidence/alignment_scores.csv |
| `AlignCrossHi` | 64 | 64 | +nan | INFO (literal shift label, not a computed value) | evidence/alignment_scores.csv |

### tab:runtime (6 rows)

| Macro | Paper | Computed | Diff | Status | Source |
|---|---|---|---|---|---|
| `EncodeSec` | 0.09 | 0.0928633 | +0.00286332 | MATCH | evidence/timing_120.csv (+recompute, median) |
| `DecSec` | 0.08 | 0.0818386 | +0.00183859 | MATCH | evidence/timing_120.csv (+recompute, median) |
| `OTTransportSec` | 0.03 | 0.0304088 | +0.000408827 | MATCH | evidence/timing_120.csv (+recompute, median) |
| `HardAssignSec` | 0.48 | 0.483833 | +0.00383298 | MATCH | evidence/timing_120.csv (+recompute, median) |
| `TMEncSec` | 0.009 | 0.0087944 | -0.000205598 | MATCH | evidence/timing_120_tm.csv (+recompute, median) |
| `TMInterpSec` | 0.003 | 0.00275007 | -0.00024993 | MATCH | evidence/timing_120_tm.csv (+recompute, median; 'gen' column) |

## Not attempted in this script (see INVENTORY.md §0/§2 for why)

These paper values have no per-pair CSV or raw feature cache in the archive
(they exist only as notebook-printed output), or require re-deriving the
Kynkaanniemi manifold-realism radii rather than reading an already-scored
per-pair value, which risks a false mismatch from RNG differences:

- `tab:app-representation` (n=40 DINO/SAM/CNT feature spread)
- `tab:app-realism` (n=100 LPIPS-control realism)
- `tab:app-position` (n=120 self-supervised position estimator)
- `tab:app-order` and the swap/rerun prose (Vacher rows unverified even against the file)
- `tab:app-repeat` (repeated-operation degradation, autoencoder row is printed-only)
- `tab:app-vacher` FID column (printed-only; timing macros ARE checked above)
- Anchor-mixture prose (`AnchorChangeA/B`), sparse-coding prose, round-trip prose
- `\GPTsec`, `\GPTcostUSD`, `\GPTOrderRatio*`, `\GPTPathMono`, `\GPTPathRtwo` (from the GPT run report, outside this data root)
- `\ResampleLPIPS`, `\GEScrambleDReal` (unverified per INVENTORY.md)
- Old 1,000-pair observer prose and `tab:app-representation`'s CNT rows (printed-only)
