"""Setup script for unified-report-generator."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="unified-report-generator",
    version="1.0.0",
    description="统一报告生成模块 — 从 Excel 台账自动生成 Markdown / Word 服务交付报告",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Oracle System Integration Center",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "openpyxl>=3.0",
    ],
    extras_require={
        "ai": [
            "matplotlib>=3.0",
        ],
        "all": [
            "matplotlib>=3.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
    ],
)
