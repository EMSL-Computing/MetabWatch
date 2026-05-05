"""
Targeted search for standards using calculated m/z values.

This script performs targeted mass feature detection on LC-MS data using pre-calculated
m/z values for standards (isotopically labeled or unlabeled). It uses CoreMS for data processing.
"""
import argparse
from pathlib import Path
from multiprocessing import Pool

import pandas as pd
from tqdm import tqdm
from matplotlib.backends.backend_pdf import PdfPages
from corems.mass_spectra.input.rawFileReader import ImportMassSpectraThermoMSFileReader
from corems.encapsulation.input.parameter_from_json import load_and_set_toml_parameters_lcms
from dotenv import load_dotenv


def set_lcms_parameters(lcms_obj, params_path=None):
    """
    Set parameters on LCMS object from TOML configuration file.
    
    Parameters
    ----------
    lcms_obj : LCMSBase
        The LCMS object to configure
    params_path : Path or str, optional
        Path to TOML parameter file. If None, uses default parameters.
    """
    load_and_set_toml_parameters_lcms(lcms_obj, params_path)


def process_single_file(raw_file, all_targets_df, config):
    """
    Process a single raw file for targeted isotope search.
    
    Parameters
    ----------
    raw_file : Path
        Path to the raw data file
    all_targets_df : pd.DataFrame
        DataFrame with all target masses (all polarities)
    config : dict
        Configuration dictionary with keys:
        - mz_tolerance_ppm: m/z tolerance in ppm
        - rt_tolerance: RT tolerance in minutes
        - plot_mass_features: whether to generate plots
        - plot_dir: directory for saving plots
        - params_path: path to CoreMS TOML parameter file (optional)
        
    Returns
    -------
    list
        List of result dictionaries for all matched mass features
    """
    
    # Load raw data
    parser = ImportMassSpectraThermoMSFileReader(raw_file)
    lcms_obj = parser.get_lcms_obj(spectra="ms1")
    assert lcms_obj is not None, "Failed to instantiate LCMS object."
    
    # Set parameters
    set_lcms_parameters(lcms_obj, config.get('params_path'))
    
    # Get polarity and filter targets
    polarity = lcms_obj.polarity
    target_df = all_targets_df[all_targets_df['polarity'] == polarity].copy()
    
    # Prepare target search dictionary
    target_search_dict = {
        "target_mz_list": target_df["mz"].tolist(),
        "target_rt_list": target_df["retention_time"].tolist(),
        "mz_tolerance_ppm": config['mz_tolerance_ppm'],
        "rt_tolerance": config['rt_tolerance'],
        "type": "internal standard"
    }
    
    # Perform targeted search
    lcms_obj.find_mass_features(
        targeted_search=True,
        target_search_dict=target_search_dict
    )
    
    # Integrate and add MS data
    lcms_obj.integrate_mass_features()
    lcms_obj.add_associated_ms1(use_parser=False, spectrum_mode="profile")
    lcms_obj.add_associated_ms2_dda(use_parser=True, spectrum_mode="centroid")
    
    # Export to DataFrame
    mf_df = lcms_obj.mass_features_to_df(drop_na_cols=True)
    
    # Match mass features to targets
    file_results = []
    for idx, mf_row in mf_df.iterrows():
        mf_mz = mf_row.get('mz')
        mf_rt = mf_row.get('scan_time')
                    
        # Find matching targets within tolerance
        mz_ppm_diff = abs((target_df['mz'] - mf_mz) / target_df['mz'] * 1e6)
        rt_diff = abs(target_df['retention_time'] - mf_rt)
        
        matches = target_df[
            (mz_ppm_diff <= config['mz_tolerance_ppm']) & 
            (rt_diff <= config['rt_tolerance'])
        ]
        
        # Keep all matches within tolerance
        for match_idx, match_row in matches.iterrows():
            result = {
                'mf_id': idx,
                'filename': raw_file.name,
                'refmet_name': match_row['refmet_name'],
                'ion_type': match_row['ion_type'],
                'target_mz': match_row['mz'],
                'target_rt': match_row['retention_time'],
                'observed_mz': mf_mz,
                'observed_rt': mf_rt,
                'mz_error_ppm': (mf_mz - match_row['mz']) / match_row['mz'] * 1e6,
                'rt_error': mf_rt - match_row['retention_time']
            }
            
            # Add isotope_label if present in target data
            if 'isotope_label' in match_row.index and pd.notna(match_row['isotope_label']) and match_row['isotope_label'] != '':
                result['isotope_label'] = match_row['isotope_label']
            
            # Add other columns from mass features dataframe
            for col in mf_df.columns:
                if col not in result:
                    result[col] = mf_row[col]
            
            file_results.append(result)
    
    # Apply filters before plotting (if specified)
    if config.get('min_area', 0) > 0 or config.get('min_intensity', 0) > 0:
        filtered_results = []
        for result in file_results:
            include = True
            if config.get('min_area', 0) > 0:
                if result.get('area', 0) < config['min_area']:
                    include = False
            if config.get('min_intensity', 0) > 0:
                if result.get('intensity', 0) < config['min_intensity']:
                    include = False
            if include:
                filtered_results.append(result)
        file_results = filtered_results
    
    # Generate plots if requested (must be done while lcms_obj is in scope)
    if config['plot_mass_features'] and len(file_results) > 0:
        plot_dir = config['plot_dir']
        plot_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_filename = plot_dir / f"{raw_file.stem}_mass_features.pdf"
        
        # Group results by mf_id
        mf_candidates = {}
        mf_observed = {}
        for result in file_results:
            mf_id = result['mf_id']
            if mf_id not in mf_candidates:
                mf_candidates[mf_id] = []
                mf_observed[mf_id] = {
                    'mz': result['observed_mz'],
                    'rt': result['observed_rt'],
                    'area': result.get('area', 'N/A'),
                    'intensity': result.get('intensity', 'N/A')
                }
            # Build candidate label with optional isotope_label
            isotope_str = f" ({result['isotope_label']})" if result.get('isotope_label') else ""
            candidate_label = (f"{result['refmet_name']}{isotope_str} {result['ion_type']} "
                             f"[Target m/z: {result['target_mz']:.4f}, RT: {result['target_rt']:.2f}]")
            if candidate_label not in mf_candidates[mf_id]:
                mf_candidates[mf_id].append(candidate_label)
        
        # Create multi-page PDF
        with PdfPages(pdf_filename) as pdf:
            for mf_id, candidates in sorted(mf_candidates.items()):
                fig = lcms_obj.mass_features[mf_id].plot()
                candidates_str = "\n".join(candidates)
                obs = mf_observed[mf_id]
                area_str = f"{obs['area']:.2e}" if isinstance(obs['area'], (int, float)) else obs['area']
                intensity_str = f"{obs['intensity']:.2e}" if isinstance(obs['intensity'], (int, float)) else obs['intensity']
                fig.suptitle(f"Mass Feature {mf_id} [Observed m/z: {obs['mz']:.4f}, RT: {obs['rt']:.2f}, "
                            f"Area: {area_str}, Intensity: {intensity_str}]\n"
                            f"Candidates:\n{candidates_str}", 
                            fontsize=8, y=0.98)
                fig.tight_layout()
                pdf.savefig(fig)
                fig.clf()

    
    return file_results


def apply_filters(results_df, min_area=0, min_intensity=0):
    """
    Apply post-processing filters to results.
    
    Parameters
    ----------
    results_df : pd.DataFrame
        Results dataframe
    min_area : float
        Minimum peak area threshold
    min_intensity : float
        Minimum peak intensity threshold
        
    Returns
    -------
    pd.DataFrame
        Filtered results
    """
    initial_count = len(results_df)
    
    if min_area > 0 and 'area' in results_df.columns:
        results_df = results_df[results_df['area'] >= min_area]
    
    if min_intensity > 0 and 'intensity' in results_df.columns:
        results_df = results_df[results_df['intensity'] >= min_intensity]
    
    if len(results_df) < initial_count:
        print(f"Filtered: {initial_count} -> {len(results_df)} results")
    
    return results_df


def main(target_masses_csv, output_dir, raw_files, config):
    """
    Main function to process isotope targeted search.
    
    Parameters
    ----------
    target_masses_csv : Path
        Path to target masses CSV file
    output_dir : Path
        Directory for output files
    raw_files : list of Path
        List of raw files to process
    config : dict
        Configuration dictionary with analysis parameters
    """
    # Load target masses
    print(f"Loading target masses from {target_masses_csv}")
    all_targets_df = pd.read_csv(target_masses_csv)
    print(f"Loaded {len(all_targets_df)} targets ({len(all_targets_df[all_targets_df['polarity'] == 'positive'])} positive, "
          f"{len(all_targets_df[all_targets_df['polarity'] == 'negative'])} negative)")
    
    # Process files
    print(f"\nProcessing {len(raw_files)} file(s)...")
    
    all_results = []
    
    # Process files with or without multiprocessing based on n_cores
    n_cores = config.get('n_cores', 1)
    if n_cores > 1 and len(raw_files) > 1:
        print(f"Using multiprocessing with {n_cores} worker(s)")
        
        # Create partial function with fixed arguments
        from functools import partial
        process_func = partial(process_single_file, all_targets_df=all_targets_df, config=config)
        
        with Pool(processes=n_cores) as pool:
            results_list = list(tqdm(pool.imap(process_func, raw_files), total=len(raw_files), desc="Processing files"))
        
        # Flatten results
        for file_results in results_list:
            all_results.extend(file_results)
    else:
        # Sequential processing with progress bar
        for raw_file in tqdm(raw_files, desc="Processing files"):
            file_results = process_single_file(raw_file, all_targets_df, config)
            all_results.extend(file_results)
    
    # Combine and filter results
    print("\nCombining results...")
    results_df = pd.DataFrame(all_results)
    
    # Note: Filtering already applied in process_single_file before plotting and returning results
    
    # Summary and save
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {len(raw_files)}")
    print(f"Total matches: {len(results_df)}")
    if len(results_df) > 0:
        print(f"Unique compounds: {results_df['refmet_name'].nunique()}")
    
    # Save results
    output_file = output_dir / config['output_filename']
    results_df.to_csv(output_file, index=False)
    print(f"\nResults saved to: {output_file}")
    
    print("\nDone!")


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Targeted search for standards using calculated m/z values."
    )
    
    # Required arguments
    parser.add_argument(
        "--raw_data_dir",
        type=Path,
        required=True,
        help="Directory containing raw data files (.raw)"
    )
    parser.add_argument(
        "--target_masses",
        type=Path,
        required=True,
        help="Path to CSV file with target masses"
    )
    parser.add_argument(
        "--output_filename",
        type=str,
        required=True,
        help="Name of output CSV file (e.g., 'results.csv')"
    )
    
    # Optional arguments
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("data"),
        help="Directory for output files (default: data)"
    )
    parser.add_argument(
        "--params_path",
        type=Path,
        default=Path("data/corems_params/monet_hilic_corems_lcms_params.toml"),
        help="Path to CoreMS TOML parameter file (default: data/corems_params/monet_hilic_corems_lcms_params.toml)"
    )
    parser.add_argument(
        "--mz_tolerance_ppm",
        type=float,
        default=5.0,
        help="m/z tolerance in ppm (default: 5.0)"
    )
    parser.add_argument(
        "--rt_tolerance",
        type=float,
        default=0.5,
        help="RT tolerance in minutes (default: 0.5)"
    )
    parser.add_argument(
        "--min_area",
        type=float,
        default=1E4,
        help="Minimum peak area threshold (default: 1E4)"
    )
    parser.add_argument(
        "--min_intensity",
        type=float,
        default=0,
        help="Minimum peak intensity threshold (default: 0)"
    )
    parser.add_argument(
        "--n_cores",
        type=int,
        default=1,
        help="Number of cores for parallel processing (default: 1)"
    )
    parser.add_argument(
        "--plot_mass_features",
        action="store_true",
        help="Generate plots for mass features (default: False)"
    )
    parser.add_argument(
        "--plot_dir",
        type=Path,
        help="Directory for saving plots (required if --plot_mass_features is set)"
    )
    
    args = parser.parse_args()
    
    # Validate plot_dir requirement
    if args.plot_mass_features and args.plot_dir is None:
        parser.error("--plot_dir is required when --plot_mass_features is set")
    
    # Get raw files
    raw_files = list(args.raw_data_dir.glob("*.raw"))
    if not raw_files:
        raise ValueError(f"No .raw files found in {args.raw_data_dir}")
    
    # Build config dictionary
    config = {
        'params_path': args.params_path,
        'mz_tolerance_ppm': args.mz_tolerance_ppm,
        'rt_tolerance': args.rt_tolerance,
        'plot_mass_features': args.plot_mass_features,
        'plot_dir': args.plot_dir,
        'output_filename': args.output_filename,
        'min_area': args.min_area,
        'min_intensity': args.min_intensity,
        'n_cores': args.n_cores
    }
    
    # Run main
    main(args.target_masses, args.output_dir, raw_files, config)