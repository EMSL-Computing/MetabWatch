MetabWatch custom config
========================

This folder was created by Create custom config in the MetabWatch GUI.
Edit the files here. Packaged presets that ship with MetabWatch are not
changed.

What to do next
---------------

1. If this is a targeted config, open monitored_compounds.csv and add your
   compounds (see below). Do not Start a targeted run until that file has
   at least one compound for the polarity you are acquiring (positive or
   negative).
2. Optionally edit corems.toml if you need different CoreMS settings.
   It is a copy of the PNNL Standard RP Metabolomics method.
3. In MetabWatch, Config source should already be Custom JSON pointing at
   metabwatch_config.json. Click Start.
4. To reuse later: Custom JSON -> Browse -> this metabwatch_config.json.

Files
-----

metabwatch_config.json
    Pipeline settings (folders, tolerances, targeted vs untargeted)

corems.toml
    CoreMS processing parameters (RP starter copy)

monitored_compounds.csv  (targeted only)
    Compound list. Header only until you add rows. Untargeted configs
    do not include this file.

README.txt
    These instructions

What the keys in metabwatch_config.json mean
--------------------------------------------

You can edit this JSON in a text editor. Keep the quotes and commas.
Paths are absolute (full paths). If you move this folder, update
corems_params and (when targeted) qc_compounds. Update input_folder
and output_folder if those locations changed.

input_folder
    Folder that contains the Thermo .raw files to process.

output_folder
    Folder where results go (dashboard, match CSVs, exports).

corems_params
    Path to corems.toml in this folder. That file is a copy of the
    PNNL Standard RP Metabolomics CoreMS settings.

targeted
    true  = look for the compounds listed in monitored_compounds.csv
    false = untargeted: build a peak list from the first matching file

polarity  (optional)
    positive or negative. When set, the run locks before the first sample.
    Omit this key (or leave it blank) to lock from the first successful file.
    Auto in Create custom config does not write this key.

project_id  (optional)
    Only process files whose name contains this text (not case-sensitive).
    Omit this key, or use an empty string, for no extra filter. The
    sample-name filter still applies.

qc_compounds  (targeted only)
    Path to monitored_compounds.csv in this folder. Fill that CSV
    before a targeted run.

top_n  (untargeted only)
    How many of the largest peaks from the first matching file to
    keep as the search list. Default is 100.

mz_tolerance_ppm
    How close a measured m/z must be to a listed compound, in parts
    per million. Default here is 5.

rt_tolerance
    How close a measured retention time must be, in minutes.
    Default here is 0.4.

min_area
    Peaks smaller than this integrated area are ignored.
    Default here is 20000.

sample_name_regex
    Which .raw files to process. MetabWatch looks at the file name
    without the .raw ending. The file is processed only if this
    pattern appears somewhere in that name.

    You do not have to know "regex" (regular expressions) in general.
    This field is just a text pattern. Common pieces:

    QC_Metab_(.+)
        Default for targeted. The name must contain QC_Metab_ followed
        by at least one more character.
        Matches:  QC_Metab_pos_01.raw
        Skips:    Sample_01.raw   or   QC_Metab_.raw

    (?i)Pool
        Default for untargeted. The name must contain Pool. (?i) means
        ignore capitalization, so pool, POOL, and Pool all count.
        Matches:  PoolQC_01.raw   Pooled_A.raw   pool_blank.raw
        Skips:    QC_Metab_pos_01.raw

    QC
        Process any file whose name contains QC.

    If a file does not match, it is skipped (not an error). Wrong
    pattern is the usual reason "nothing ran."

    Leave the value in quotes. Do not add extra spaces inside the
    quotes unless those spaces are part of the file name.

Fill the compound list before a targeted search
----------------------------------------------

monitored_compounds.csv is a blank template. Add one row per compound in
Excel or a text editor. Keep the header row. An empty list fails when the
first sample is processed.

Required columns (in this order):

compound_name,ion_type,mz,retention_time,polarity

Example row:

Caffeine,[M+H]+,195.0877,4.20,positive

- polarity must be positive or negative (lowercase).
- mz and retention_time (minutes) must be numbers.
- ion_type is a label such as [M+H]+ or [M-H]-. Must include the + or - symbol to match with expected polarity.
- Do not put comment lines in the CSV.

Untargeted search
-----------------

If this config is untargeted, there is no compound list in this folder.
The first sample that matches the sample-name filter builds the search space
(untargeted_search_space.csv under the output folder). Later samples are
matched against that list.

Other notes
-----------

- CLI equivalent: metabwatch --config metabwatch_config.json
- See "What the keys in metabwatch_config.json mean" above for paths,
  tolerances, and the sample-name filter.
