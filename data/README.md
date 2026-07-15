# Files in data folder

1. `original_QC_list.xlsx`: This file was acquired from W. Kew April 2026 and is the basis for the current HILIC QC workflow. It contains the list of standards and their expected properties (e.g. m/z, retention time) that are used for the targeted search in the pipeline.
2. `corems_params`: This directory contains the CoreMS parameter files used for the QC analysis. The HILIC LC-MS params file is `corems_params/monet_hilic_corems_lcms_params.toml`.
3. `qc_search_space`: This directory contains the CSV file that defines the search space for the targeted search of standards used by the current HILIC workflow.
