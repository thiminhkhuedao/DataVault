from setuptools import setup, find_packages

setup(
    name="datavault-cli",
    version="1.0.0",
    description="Cryptographic provenance for AI training datasets",
    author="thiminhkhuedao",
    url="https://github.com/thiminhkhuedao/DataVault",
    py_modules=["datavault", "vault_core", "chain", "signing", "row_tracker", "dashboard", "pi_bridge", "migrate"],
    python_requires=">=3.6",
    entry_points={"console_scripts": ["datavault=datavault:main"]},
)