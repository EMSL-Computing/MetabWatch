# LCMS QC
This repository contains scripts for performing quality control (QC) on liquid chromatography-mass spectrometry (LCMS) data using the CoreMS software.  The scripts are designed to process raw LCMS data files, perform a targeted search for specific compounds.

# CoreMS
This uses a DEVELOPMENT version of CoreMS available at https://github.com/EMSL-Computing/CoreMS/commit/88f6d0021ed594b5d0a3efe6285f8379858fd039 which is not yet merged into main (>v4.0.0).  We recommend using the Docker approach above since it will ensure the correct version of CoreMS is used and will handle the installation of CoreMS, its dependencies, and some tricky dependencies needed to read .raw files (e.g., Thermo .raw files).