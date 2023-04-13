from bias_correction.utils_bc.network import detect_network
from bias_correction.utils_bc.utils_config import assert_input_for_skip_connection, \
    sort_input_variables, \
    adapt_distribution_strategy_to_available_devices, \
    init_learning_rate_adapted, \
    detect_variable, \
    get_idx_speed_and_dir_variables, \
    define_input_variables
from bias_correction.config._config import config

# Architecture
config["details"] = "batch_size_256_archi_25_10_50_epoch_15"
config[
    "global_architecture"] = "double_ann"
config["restore_experience"] = "2022_12_7_labia_v8"

# ann_v0
config["disable_training_cnn"] = True
config["type_of_output"] = "output_speed"
config["nb_units"] = [50, 10]
config["nb_units_speed"] = [50, 10]
config["nb_units_dir"] = [50, 10]
config["use_bias"] = True

# General
config["batch_normalization"] = False
config["activation_dense"] = "gelu"
config["activation_dense_speed"] = "selu"
config["activation_dense_dir"] = "gelu"
config["dropout_rate"] = 0.35
config["dropout_rate_speed"] = 0.25
config["dropout_rate_dir"] = 0.35
config["final_skip_connection"] = True
config["distribution_strategy"] = None
config["prefetch"] = "auto"

# Skip connections in dense network
config["dense_with_skip_connection"] = False

# Hyperparameters
config["batch_size_speed"] = 256
config["batch_size_dir"] = 128
config["epochs_speed"] = 10
config["epochs_dir"] = 5
config["learning_rate_speed"] = 0.001
config["learning_rate_dir"] = 0.001

# Optimizer
config["optimizer"] = "Adam"
config["args_optimizer"] = [config["learning_rate"]]
config["kwargs_optimizer"] = {}

# Initializer
config["initializer"] = "GlorotNormal"
config["args_initializer"] = []
config["kwargs_initializer"] = {"seed": 42}

# Input CNN
config["input_cnn"] = False
config["use_input_cnn_dir"] = False
config["use_batch_norm_cnn"] = False
config["activation_cnn"] = "gelu"
config["threshold_null_speed"] = 1
config["use_normalization_cnn_inputs"] = True

# Inputs pre-processing
config["standardize"] = True
config["shuffle"] = True

# Quick test
config["quick_test"] = False
config["quick_test_stations"] = ["ALPE-D'HUEZ"]

# Input variables
config["input_speed"] = ["alti",
                         "ZS",
                         "Tair",
                         "LWnet",
                         "SWnet",
                         "CC_cumul",
                         "BLH",
                         "tpi_500",
                         "curvature",
                         "mu",
                         "laplacian",
                         'Wind90',
                         'Wind87',
                         'Wind84',
                         'Wind75',
                         "Wind",
                         "Wind_DIR"]
config["input_dir"] = ['aspect', 'tan(slope)', 'Wind', 'Wind_DIR']
config["map_variables"] = ["topos", "aspect", "tan_slope", "tpi_300", "tpi_600"]
config["compute_product_with_wind_direction"] = True

# Labels
config["labels"] = ['vw10m(m/s)']
config["wind_nwp_variables"] = ["Wind", "Wind_DIR"]
config["wind_temp_variables"] = ['Tair']

# Dataset
config["unbalanced_dataset"] = False
config["unbalanced_threshold"] = 2

# Callbacks
config["callbacks"] = ["ModelCheckpoint"]
config["args_callbacks"] = {"ReduceLROnPlateau": [],
                            "EarlyStopping": [],
                            "ModelCheckpoint": [],
                            "TensorBoard": [],
                            "CSVLogger": [],
                            "CSVLogger_dir": [],
                            "LearningRateWarmupCallback": [],
                            "FeatureImportanceCallback": [],
                            "BroadcastGlobalVariablesCallback": [],
                            "MetricAverageCallback": [],
                            "learning_rate_decay": [],
                            }

config["kwargs_callbacks"] = {"ReduceLROnPlateau": {"monitor": "val_loss",
                                                    "factor": 0.5,  # new_lr = lr * factor
                                                    "patience": 3,
                                                    "min_lr": 0.0001},

                              "EarlyStopping": {"monitor": "val_loss",
                                                "min_delta": 0.01,
                                                "patience": 5,
                                                "mode": "min",
                                                "restore_best_weights": False},

                              "ModelCheckpoint": {"min_delta": 0.01,
                                                  "monitor": "loss",
                                                  "save_best_only": True,
                                                  "save_weights_only": False,
                                                  "mode": "min",
                                                  "save_freq": "epoch"},

                              "TensorBoard": {"profile_batch": '20, 50',
                                              "histogram_freq": 1},

                              "LearningRateWarmupCallback": {"warmup_epochs": 5,
                                                             "verbose": 1},

                              "FeatureImportanceCallback": {},

                              "BroadcastGlobalVariablesCallback": {},

                              "MetricAverageCallback": {},

                              "CSVLogger": {},

                              "CSVLogger_dir": {},

                              "learning_rate_decay": {},
                              }

# Metrics
config["metrics"] = ["tf_mae", "tf_rmse", "tf_mbe"]

# Split
config["split_strategy_test"] = "time_and_space"  # "time", "space", "time_and_space", "random"
config["split_strategy_val"] = "time_and_space"

# Random split
config["random_split_state_test"] = 50  # Float. Default = 50
config["random_split_state_val"] = 55  # Float. Default = 55

# Time split
config["date_split_train_test"] = "2019-10-01"
config["date_split_train_val"] = "2019-10-01"

# Select test and val stations
config["parameters_split_test"] = ["alti", "tpi_500_NN_0", "mu_NN_0", "laplacian_NN_0", "Y", "X"]
config["parameters_split_val"] = ["alti", "tpi_500_NN_0"]
config["country_to_reject_during_training"] = ["pyr", "corse"]
config["metric_split"] = "rmse"

# Space split
config["stations_test"] = ['Col du Lac Blanc', 'GOE', 'WAE', 'TGKAL', 'LAG', 'AND', 'CHU', 'SMM', 'ULR', 'WFJ', 'TICAM',
                           'SCM', 'MMMEL', 'INNRED', 'MMBIR', 'MMHIW', 'MMLOP', 'TGALL', 'GAP', 'BAS', 'STK', 'PLF',
                           'MVE', 'SAG', 'MLS', 'MAR', 'MTE', 'MTR', 'CHZ', 'SIA', 'COV', 'MMSTA', 'BIV', 'ANT',
                           'TGDIE', 'CHM', 'TGARE', 'TALLARD', 'LE CHEVRIL-NIVOSE', 'GOR', 'MMMUE', 'INT', 'BIE', 'EIN',
                           'RUE', 'QUI', 'NEU', 'MMNOI', 'LE GUA-NIVOSE', 'GIH', 'AEG', 'MOE', 'LUG', 'TGNUS', 'BEH']
config["stations_val"] = []
config["stations_to_reject"] = ["Vallot", "Dome Lac Blanc", "MFOKFP"]

# Intermediate output
config["get_intermediate_output"] = True

# Custom loss
config["loss"] = "pinball_proportional"
config["args_loss"] = {"mse": [],
                       "penalized_mse": [],
                       "mse_proportional": [],
                       "mse_power": [],
                       "pinball": [],
                       "pinball_proportional": [],
                       "pinball_weight": [],
                       "cosine_distance": []}
config["kwargs_loss"] = {"mse": {},
                         "penalized_mse": {"penalty": 10,
                                           "speed_threshold": 5},
                         "mse_proportional": {"penalty": 1},
                         "mse_power": {"penalty": 1,
                                       "power": 2},
                         "pinball": {"tho": 0.85},
                         "pinball_proportional": {"tho": 0.6},
                         "pinball_weight": {"tho": 0.95},
                         "cosine_distance": {"power": 1}}

# Do not modify: assert inputs are correct
config = define_input_variables(config)
config = assert_input_for_skip_connection(config)
config = sort_input_variables(config)
config = adapt_distribution_strategy_to_available_devices(config)
config = init_learning_rate_adapted(config)
config["nb_input_variables"] = len(config["input_variables"])
config = detect_variable(config)
config = get_idx_speed_and_dir_variables(config)

list_variables = ['name', 'date', 'lon', 'lat', 'alti', 'T2m(degC)', 'vw10m(m/s)',
                  'winddir(deg)', 'HTN(cm)', 'Tair', 'T1', 'ts', 'Tmin', 'Tmax', 'Qair',
                  'Q1', 'RH2m', 'Wind_Gust', 'PSurf', 'ZS', 'BLH', 'Rainf', 'Snowf',
                  'LWdown', 'LWnet', 'DIR_SWdown', 'SCA_SWdown', 'SWnet', 'SWD', 'SWU',
                  'LHF', 'SHF', 'CC_cumul', 'CC_cumul_low', 'CC_cumul_middle',
                  'CC_cumul_high', 'Wind90', 'Wind87', 'Wind84', 'Wind75', 'TKE90',
                  'TKE87', 'TKE84', 'TKE75', 'TT90', 'TT87', 'TT84', 'TT75', 'SWE',
                  'snow_density', 'snow_albedo', 'vegetation_fraction', 'Wind',
                  'Wind_DIR', 'U_obs', 'V_obs', 'U_AROME', 'V_AROME', "month", "hour"]
