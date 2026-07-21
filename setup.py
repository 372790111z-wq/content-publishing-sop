"""Compatibility metadata for Python 3.9 machines with older setuptools."""

from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).resolve().parent

setup(
    name="content-publishing-sop",
    version=(ROOT / "VERSION").read_text(encoding="utf-8").strip(),
    description="Cross-IDE content production, validation and publishing governance toolkit",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=["content_publishing"],
    package_data={"content_publishing": ["platforms.json"]},
    python_requires=">=3.9",
    entry_points={"console_scripts": ["content-publishing=content_publishing.cli:main"]},
)
