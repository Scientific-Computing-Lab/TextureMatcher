# Post-hoc visual quality-control review

This review was performed only after generation and is descriptive. It did not
change inclusion, selection, or any metric. All outputs remain in the manifest
and gallery.

The automatic edge/seam heuristic flagged six of 444 unique request outputs
(eight of 516 logical cells after declared aliases) as
`suspicious_panel_layout`. Visual review found that five are coherent repeated
grid, stripe, or ruffle textures whose strong internal seams triggered the
conservative detector: S2 pairs 0362, 0705, and 0838; S4 pair 0838 AB repeat 2;
and S4 pair 0657 BA repeat 1.

S3/P0 pair 0841 is a plausible prompt-contract violation: its upper region is
vertical striping while its lower region is a distinct chevron band, producing
a panel-like two-region composition. It is retained without correction or
replacement. No output was flagged as corrupt, blank, near-uniform, or as
having a suspicious outer border.

The complete, non-cherry-picked review sheets are in
[`../runs/full_pending_approval_20260901/FULL_GALLERY.md`](../runs/full_pending_approval_20260901/FULL_GALLERY.md).
