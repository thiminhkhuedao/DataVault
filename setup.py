from setuptools import setup

setup(
    name="datavault-cli",
    version="1.0.0",
    description="Cryptographic provenance and version control for AI training datasets",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Ry Nguyen",
    author_email="thiminhkhuedao@gmail.com",
    url="https://github.com/thiminhkhuedao/DataVault",
    py_modules=["datavault","vault_core","chain","signing","row_tracker","dashboard","pi_bridge","migrate"],
    python_requires=">=3.6",
    entry_points={"console_scripts": ["datavault=datavault:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Version Control",
    ],
    keywords="data provenance versioning AI machine-learning CSV sha256",
)