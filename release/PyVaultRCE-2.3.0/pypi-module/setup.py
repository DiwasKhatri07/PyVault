from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="PyVaultRCE",
    version="2.3.0",
    author="PyVault",
    description="Remote Code Execution & Hosting client for PyVault — source never exposed",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "cryptography>=41.0.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries",
        "Topic :: Security",
        "Topic :: Internet :: WWW/HTTP",
    ],
    keywords="remote execution code hosting vault rce session",
    entry_points={},
)
