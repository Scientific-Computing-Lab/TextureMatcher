from setuptools import find_packages, setup

# Tier 1 (score_only.py) needs only the base dependencies: CPU only, no GPU and
# no CNT / Texture Mixer install. Tiers 2 and 3 use the extras plus
# install/cnt.sh and install/texture_mixer.sh.
setup(
    name="texton-matching",
    version="0.1.0",
    description="Texture Interpolation as Texton Matching: reproduction package",
    license="MIT",
    python_requires=">=3.9",
    packages=find_packages(include=["texton_matching*"]),
    install_requires=["numpy", "scipy", "pandas", "pillow"],
    extras_require={
        "scoring": ["torch", "torchvision", "timm>=1.0.11", "lpips", "einops"],
        "cnt": ["torch", "torchvision", "timm>=1.0.11", "lpips", "einops",
                "hydra-core>=1.3", "omegaconf>=2.3", "antlr4-python3-runtime==4.9.3"],
    },
)
