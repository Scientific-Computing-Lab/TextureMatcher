"""texton_matching: reproduction package for "Texton Matching for Texture Interpolation".

Submodules are added incrementally. `scoring` and `paths` are CPU-only and have
no CNT / torch / TensorFlow dependency, so they work in a plain numpy+scipy+pandas
environment (see env/score-only.yml). Modules that wrap CNT or Texture Mixer
(`cnt.py`, `texture_mixer/`) require their own GPU environments and guard their
imports accordingly.
"""
