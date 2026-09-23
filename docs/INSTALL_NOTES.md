# Install notes

Design notes for the scripts in `install/`. The README lists the commands; this
file records why the scripts are written the way they are.

## `install/scoring.sh`

Installs torch and torchvision (Inception-v3 weights download on first use),
DINOv2, LPIPS and einops. DINOv2 is loaded through timm as
`vit_small_patch14_dinov2.lvd142m`, which is the loader every scoring notebook
used, rather than `torch.hub`. timm re-hosts the same released weights.
`rescore.py` sets `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` before importing timm so that
Colab does not prompt for a Hugging Face token; the model download is public.

## `install/cnt.sh`

A shell version of the install cell used in `colab/reproduce.ipynb`
(Colab T4, Python 3.13).

- CNT is cloned at the pinned commit `07269302610c92ce38e2dbbe31c492fd09e1c73e`.
- The checkpoint downloads first, so a failed download stops the script before
  the detectron2 build (5 to 10 minutes). A missing or under-1 GB checkpoint is
  the only hard failure.
- `requirements.in` is installed as one tolerated call, not line by line. Line
  by line installs CNT's older pins, which fail at runtime on Python 3.13: old
  hydra/omegaconf pull in `antlr4-python3-runtime` 4.8
  (`ModuleNotFoundError: typing.io`), and old timm raises
  `ValueError: mutable default MaxxVitConvCfg`.
- `import detectron2` is checked directly and detectron2 is installed if missing.
- The script ends with
  `pip install -U timm "hydra-core>=1.3" "omegaconf>=2.3" "antlr4-python3-runtime==4.9.3"`,
  which resolves the runtime failures above regardless of what `requirements.in`
  installed.
- The checkpoint's sha256 prefix is compared with the recorded value.
- `CNTModel.__init__` changes into the CNT root while building the model,
  because the Mask2Former config paths resolve relative to it.

## `install/texture_mixer.sh` and `install/environment_tm.yml`

Texture Mixer runs in its own conda environment because it replaces the global
`tensorflow` module.

- The original code targets TF1 (`tf.contrib.slim`). The experiments ran it on
  the TF2 install of Colab through `tensorflow.compat.v1`, `tf_slim` registered
  as `tensorflow.contrib.{slim,framework,layers}`, and `sys.modules["tensorflow"]`
  pointing at the v1 API. `environment_tm.yml` reproduces that setup; a genuine
  TF 1.15 environment does not install on current CUDA versions.
- `tensorflow` has no upper version bound, for the same reason `requirements.in`
  is not installed line by line in `cnt.sh`.
- Two `x.shape.ndims is 0/1` identity comparisons in `tfutil.py` are patched to
  `==`.
- The checkpoint downloads right after the clone and is size-checked (at least
  100 MB) and hash-checked.
- Torch is never imported in this environment. `experiments/tm_1000.py` renders,
  then prints the `rescore.py` command to run in the scoring environment.

## `install/vacher.sh`

Clones the Vacher et al. optimization baseline at its default branch; the
experiments did not pin a commit. Used by `experiments/vacher_50.py`.

## Checkpoints

Both checkpoints are public Google Drive shares taken from the model authors'
own repositories: CNT's `finetuned-model256.ckpt` (1.27 GB, sha256 prefix
`a3f80515ac5d8c8d`) and Texture Mixer's `earth_texture/network-final.pkl`
(233,627,047 bytes; full sha256 in `install/texture_mixer.sh`). Both files were
downloaded and hash-checked. The CNT project page lists content from an
unrelated project, so the GitHub README is the reference for CNT's checkpoint.
