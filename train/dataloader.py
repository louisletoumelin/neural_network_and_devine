import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.python.data.ops.dataset_ops import DatasetV2

from copy import copy
import pickle
from sklearn.utils import shuffle
from sklearn.model_selection import train_test_split
from typing import Optional, Tuple, Union, Any, List, MutableSequence, Generator
from dataclasses import dataclass

from bias_correction.train.metrics import get_metric
from bias_correction.train.wind_utils import wind2comp


class MapGeneratorUncentered:

    def __init__(self,
                 names: MutableSequence[str],
                 idx_x: np.ndarray,
                 idx_y: np.ndarray,
                 config: dict
                 ) -> None:

        loader = Loader(config)

        try:
            self.names = names.values
        except AttributeError:
            self.names = names

        self.idx_x = idx_x
        self.idx_y = idx_y
        self.idx_center = 140
        self.list_dict_topos = loader.load_large_topos()

    def __call__(self):
        for name, ix, iy in zip(self.names, self.idx_x, self.idx_y):
            y_l = (self.idx_center + iy) - 70
            y_r = (self.idx_center + iy) + 70
            x_l = (self.idx_center + ix) - 70
            x_r = (self.idx_center + ix) + 70
            yield self.list_dict_topos[name]["data"][y_l:y_r, x_l:x_r, :]


class MapGenerator:

    def __init__(self,
                 names_map: MutableSequence,
                 names: MutableSequence[str],
                 config: dict
                 ) -> None:

        loader = Loader(config)

        try:
            self.names = names.values
        except AttributeError:
            self.names = names

        self.list_dict_topos = [loader.load_dict(name_map) for name_map in names_map]

    def __call__(self):
        if len(self.list_dict_topos) == 0:
            for name in self.names:
                yield self.list_dict_topos[0][name]["data"]
        else:
            for name in self.names:
                yield np.concatenate([self.list_dict_topos[i][name]["data"] for i in range(len(self.list_dict_topos))],
                                     axis=-1)


class MapGeneratorCustom:

    def __init__(self,
                 names: MutableSequence[str],
                 dict_topo: dict
                 ) -> None:

        try:
            self.names = names.values
        except AttributeError:
            self.names = names

        self.dict_topo = dict_topo

    def __call__(self):
        for name in self.names:
                yield self.dict_topo[name]["data"]


class MeanGenerator:

    def __init__(self,
                 mean: MutableSequence[float],
                 length: Union[float, int]
                 ) -> None:
        self.mean = mean
        self.length = length

    def __call__(self):
        for i in range(self.length):
            yield self.mean


class Batcher:

    def __init__(self,
                 config: dict
                 ) -> None:
        self.config = config

    def _get_prefetch(self):
        if self.config.get("prefetch") == "auto":
            return tf.data.AUTOTUNE
        else:
            return self.config["prefetch"]

    def batch_train(self,
                    dataset: tf.data.Dataset
                    ) -> DatasetV2:
        # Before .cache before prefetch
        return dataset \
            .batch(batch_size=self.config["global_batch_size"]) \
            .prefetch(self._get_prefetch())

    def batch_test(self,
                   dataset: tf.data.Dataset
                   ) -> DatasetV2:
        print("\n\nWARNING: usually test data are not batched")
        return dataset.batch(batch_size=self.config[
            "global_batch_size"])  # todo put raise NotImplementedError("Test data are not batched")

    def batch_val(self,
                  dataset: tf.data.Dataset
                  ) -> DatasetV2:
        return dataset.batch(batch_size=self.config["global_batch_size"])


class Splitter:

    def __init__(self, config: dict) -> None:
        self.config = config

    def _split_by_time(self,
                       time_series: pd.DataFrame,
                       mode: Union[str, None] = None,
                       **kwargs: Any
                       ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        assert mode is not None, "mode must be specified"

        time_series_train = time_series[time_series.index < self.config[f"date_split_train_{mode}"]]
        time_series_test = time_series[time_series.index >= self.config[f"date_split_train_{mode}"]]

        return time_series_train, time_series_test

    def _split_by_space(self,
                        time_series: pd.DataFrame,
                        mode: Union[str, None] = None,
                        **kwargs: Any
                        ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        assert mode is not None, "mode must be specified"

        time_series_train = time_series[time_series["name"].isin(self.config[f"stations_train"])]
        time_series_test = time_series[time_series["name"].isin(self.config[f"stations_{mode}"])]

        return time_series_train, time_series_test

    def _split_random(self,
                      time_series: pd.DataFrame,
                      mode: Union[str, None] = None,
                      **kwargs: Any
                      ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        assert mode is not None, "mode must be specified"

        str_test_size = f"random_split_test_size_{mode}"
        str_random_state = f"random_split_state_{mode}"

        if self.config["quick_test"] and mode == "test":
            test_size = 0.05
        elif self.config["quick_test"] and mode == "val":
            test_size = 0.01
        else:
            test_size = self.config[str_test_size]

        return train_test_split(time_series, test_size=test_size, random_state=self.config[str_random_state])

    def _split_time_and_space(self,
                              time_series: pd.DataFrame,
                              mode: Union[str, None] = None,
                              **kwargs: Any
                              ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        assert mode is not None, "mode must be specified"

        time_series_train, time_series_test = self._split_by_space(time_series, mode)
        time_series_train, _ = self._split_by_time(time_series_train, mode)
        _, time_series_test = self._split_by_time(time_series_test, mode)

        return time_series_train, time_series_test

    def _split_by_country(self,
                          time_series: pd.DataFrame,
                          stations: Union[pd.DataFrame, None] = None,
                          **kwargs: Any
                          ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        assert stations is not None, "stations pd.DataFrame must be specified"

        countries_to_reject = self.config["country_to_reject_during_training"]
        names_country_to_reject = stations["name"][stations["country"].isin(countries_to_reject)].values
        time_series_other_countries = time_series[time_series["name"].isin(names_country_to_reject)]
        time_series = time_series[~time_series["name"].isin(names_country_to_reject)]
        return time_series, time_series_other_countries

    def split_wrapper(self,
                      time_series: pd.DataFrame,
                      mode: str = "test",
                      stations: Union[pd.DataFrame, None] = None,
                      split_strategy: Union[str, None] = None,
                      ) -> Tuple[pd.DataFrame, pd.DataFrame]:

        split_strategy = self.config[f"split_strategy_{mode}"] if split_strategy is None else split_strategy

        strategies = {"time": self._split_by_time,
                      "space": self._split_by_space,
                      "time_and_space": self._split_time_and_space,
                      "random": self._split_random,
                      "country": self._split_by_country}

        time_series_train, time_series_test = strategies[split_strategy](time_series, mode=mode, stations=stations)

        return time_series_train, time_series_test

    def _check_split_strategy_is_correct(self) -> None:
        not_implemented_strategies_test = ["time", "space", "time", "random", "random", "random", "time", "space"]
        not_implemented_strategies_val = ["time", "time", "space", "space", "time", "time_and_space",
                                          "time_and_space", "time_and_space"]

        implemented_strategies_test = ["space", "random", "time", "space", "time_and_space", "time_and_space"]
        implemented_strategies_val = ["space", "random", "random", "random", "time_and_space", "random"]

        strat_t = self.config["split_strategy_test"]
        strat_v = self.config["split_strategy_val"]

        if (strat_t, strat_v) in zip(implemented_strategies_test, implemented_strategies_val):
            print(f"\nSplit strategy is implemented: test={strat_t}, val={strat_v}")
        elif (strat_t, strat_v) in zip(not_implemented_strategies_test, not_implemented_strategies_val):
            raise NotImplementedError(f"Split strategy test={strat_t} and val={strat_v} is not implemented")
        else:
            raise NotImplementedError("Split strategy not referenced")

    def split_train_test_val(self,
                             time_series: pd.DataFrame,
                             split_strategy: Union[str, None] = None
                             ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:

        self._check_split_strategy_is_correct()

        strat_t = self.config["split_strategy_test"]
        strat_v = self.config["split_strategy_val"]

        time_series_train, time_series_test = self.split_wrapper(time_series,
                                                                 mode="test",
                                                                 split_strategy=split_strategy)

        if "time_and_space" == strat_t and "time_and_space" == strat_v:
            ts = time_series
        else:
            ts = time_series_train

        if self.config["stations_val"]:
            time_series_train, time_series_val = self.split_wrapper(ts,
                                                                    mode="val",
                                                                    split_strategy=split_strategy)
        else:
            time_series_val = pd.DataFrame()
        return time_series_train, time_series_test, time_series_val


class Loader:

    def __init__(self, config: dict) -> None:
        self.config = config

    def load_dict(self,
                  name_map: str,
                  get_x_y: bool = False):

        dict_path = {"topos": self.config["topos_near_station"],
                     "aspect": self.config["aspect_near_station"],
                     "tan_slope": self.config["tan_slope_near_station"],
                     "tpi_300": self.config["tpi_300_near_station"],
                     "tpi_600": self.config["tpi_600_near_station"],
                     }

        with open(dict_path[name_map], 'rb') as f:
            dict_topos = pickle.load(f)

        y_l = 140 - 70
        y_r = 140 + 70
        x_l = 140 - 70
        x_r = 140 + 70
        for station in dict_topos:
            dict_topos[station]["data"] = np.reshape(dict_topos[station]["data"][y_l:y_r, x_l:x_r], (140, 140, 1))

        if get_x_y:
            for station in dict_topos:
                dict_topos[station]["x"] = dict_topos[station]["x"][x_l:x_r]
                dict_topos[station]["y"] = dict_topos[station]["y"][y_l:y_r]

        return dict_topos

    def load_large_topos(self, get_x_y: bool = False):

        with open(self.config["topos_near_station"], 'rb') as f:
            dict_topos = pickle.load(f)

        for station in dict_topos:
            dict_topos[station]["data"] = np.reshape(dict_topos[station]["data"], (280, 280, 1))

        if get_x_y:
            for station in dict_topos:
                dict_topos[station]["x"] = dict_topos[station]["x"]
                dict_topos[station]["y"] = dict_topos[station]["y"]

        return dict_topos

    def load_time_series_pkl(self) -> pd.DataFrame:
        return pd.read_pickle(self.config["time_series"])

    def load_stations_pkl(self) -> pd.DataFrame:
        return pd.read_pickle(self.config["stations"])


class ResultsSetter:

    def __init__(self, config: dict) -> None:
        self.config = config

    def has_intermediate_outputs(self,
                                 results: MutableSequence[float]
                                 ) -> Union[bool]:
        return isinstance(results, tuple) and len(results) > 1 and self.config.get("get_intermediate_output", False)

    def _nn_output2df(self,
                      result: MutableSequence[float],
                      names: MutableSequence[str],
                      name_uv: str = "UV_nn"
                      ) -> pd.DataFrame:

        df = pd.DataFrame()
        df["name"] = names
        if "component" in self.config["type_of_output"]:
            df[name_uv] = np.sqrt(result[0] ** 2 + result[1] ** 2)
        else:
            df[name_uv] = np.squeeze(result)

        return df[["name", name_uv]]

    def _prepare_intermediate_outputs(self,
                                      results: MutableSequence[float]
                                      ) -> Tuple[MutableSequence[float], str, str]:

        assert self.has_intermediate_outputs(results)

        if self.config["current_variable"] == "UV":
            results = results[1][:, 0]
        elif self.config["current_variable"] == "UV_DIR":
            if self.config["global_architecture"] == "double_ann":
                # In double_ann, intermediate output is one dimensional (either speed or direction)
                results = results[1][:, 0]
            else:
                # In other architecture, intermediate output is two
                # dimensional (one dimension for speed, the other direction)
                results = results[1][:, 1]
        str_model = "_int"
        mode_str = "int"
        return results, str_model, mode_str

    def _prepare_final_outputs(self,
                               results: MutableSequence[float]
                               ) -> MutableSequence[float]:
        if self.has_intermediate_outputs(results):
            results = results[0]
        return results

    def prepare_df_results(self,
                           results: MutableSequence[float],
                           names: MutableSequence[str],
                           mode: str = "test",
                           str_model: str = "_nn"
                           ) -> Tuple[pd.DataFrame, str]:

        if str_model == "_int":
            results, str_model, mode_str = self._prepare_intermediate_outputs(results)
        else:
            results = self._prepare_final_outputs(results)
            mode_str = mode

        name_uv = f"{self.config['current_variable']}{str_model}"
        df = self._nn_output2df(results, names, name_uv=name_uv)
        return df, mode_str


class DataHolder:

    def __init__(self):
        inputs: Union[pd.DataFrame, pd.Series]
        length: int
        labels: Union[pd.DataFrame, pd.Series]
        names: MutableSequence[str]
        predicted: Union[pd.DataFrame, pd.Series] = None


class CustomDataHandler:

    def __init__(self, config: dict) -> None:

        self.config = config
        self.variables_needed = copy(['name'] + self.config["input_variables"] + self.config["labels"])
        if "alti-zs" in self.variables_needed:
            self.variables_needed.extend(["alti", "ZS"])
        self.batcher = Batcher(config)
        self.splitter = Splitter(config)
        self.loader = Loader(config)
        self.results_setter = ResultsSetter(config)

        # Attributes defined later
        self.dict_topos = None
        self.inputs_train = None
        self.inputs_test = None
        self.inputs_val = None
        self.inputs_other_countries = None
        self.length_train = None
        self.length_test = None
        self.length_val = None
        self.length_other_countries = None
        self.labels_train = None
        self.labels_test = None
        self.labels_val = None
        self.labels_other_countries = None
        self.names_train = None
        self.names_test = None
        self.names_val = None
        self.names_other_countries = None
        self.mean_standardize = None
        self.std_standardize = None
        self.is_prepared = None
        self.predicted_train = None
        self.predicted_test = None
        self.predicted_val = None
        self.predicted_int = None
        self.predicted_other_countries = None
        self.inputs_custom = None
        self.length_custom = None
        self.names_custom = None
        self.idx_x_train = None
        self.idx_y_train = None
        self.idx_x_test = None
        self.idx_y_test = None
        self.idx_x_val = None
        self.idx_y_val = None
        self.idx_x_other_countries = None
        self.idx_y_other_countries = None

    def _select_all_variables_needed(self,
                                     df: pd.DataFrame,
                                     variables_needed: Union[bool, None] = None
                                     ) -> Union[pd.Series, pd.DataFrame]:
        variables_needed = self.variables_needed if variables_needed is None else variables_needed
        if "alti-zs" in self.variables_needed:
            df["alti-zs"] = df["alti"] - df["ZS"]
            self.variables_needed.remove("alti")
            self.variables_needed.remove("ZS")
        return df[variables_needed]

    def add_topo_carac_time_series(self,
                                   time_series: pd.DataFrame,
                                   stations: pd.DataFrame
                                   ) -> pd.DataFrame:

        for topo_carac in ["tpi_500", "curvature", "laplacian", "mu"]:
            if topo_carac in self.config["input_variables"]:
                time_series.loc[:, topo_carac] = np.nan
                for station in time_series["name"].unique():
                    value_topo_carac = stations.loc[stations["name"] == station, topo_carac + "_NN_0"].values[0]
                    time_series.loc[time_series["name"] == station, topo_carac] = value_topo_carac
        return time_series

    def add_topographic_parameters_llt(self,
                                       time_series: pd.DataFrame
                                       ) -> pd.DataFrame:
        df = pd.read_csv(self.config["path_to_topographic_parameters"] + "df_params.csv")
        for topo_carac in ['dir_canyon_w0_1_w1_10',
                           'is_canyon_w0_1_w1_10',
                           'dir_canyon_w0_5_w1_10',
                           'is_canyon_w0_5_w1_10',
                           'dir_canyon_w0_1_w1_3_thresh5',
                           'is_canyon_w0_1_w1_3_thresh5',
                           'dir_canyon_w0_4_w1_20_thresh20',
                           'is_canyon_w0_4_w1_20_thresh20',
                           'diag_7', 'diag_13', 'diag_21', 'diag_31',
                           'diag_7_r', 'diag_13_r', 'diag_21_r', 'diag_31_r',
                           'side_7', 'side_13', 'side_21', 'side_31',
                           'side_7_r', 'side_13_r', 'side_21_r', 'side_31_r',
                           'aspect', 'tan(slope)'
                           ]:
            if topo_carac in self.config["input_variables"]:
                time_series[topo_carac] = np.nan
                for station in time_series["name"].unique():
                    try:
                        value_topo_carac = df.loc[df["name"] == station, topo_carac].values[0]
                    except:

                        value_topo_carac = df.loc[df["name"] == station, topo_carac].values
                    time_series.loc[time_series["name"] == station, topo_carac] = value_topo_carac

        if self.config["compute_product_with_wind_direction"]:
            for topo_carac in ['dir_canyon_w0_1_w1_10',
                               'dir_canyon_w0_5_w1_10',
                               'dir_canyon_w0_1_w1_3_thresh5',
                               'dir_canyon_w0_4_w1_20_thresh20']:
                if topo_carac in self.config["input_variables"]:
                    time_series[topo_carac] = np.abs(
                        np.sin(np.deg2rad(time_series[topo_carac] - time_series["Wind_DIR"])))

            if 'tan(slope)' in self.config["input_variables"]:
                print("Transform tan(slope) into E.")
                # use a proper method to make the difference between directions would be better
                cos_delta = np.cos(np.deg2rad(time_series["winddir(deg)"] - time_series["aspect"]))
                time_series['tan(slope)'] = np.rad2deg(np.arctan(time_series['tan(slope)'] * cos_delta))

        return time_series

    def reject_stations(self,
                        time_series: pd.DataFrame,
                        stations: pd.DataFrame
                        ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Reject stations from inputs files as defined by the user"""
        time_series = time_series[~time_series["name"].isin(self.config["stations_to_reject"])]
        stations = stations[~stations["name"].isin(self.config["stations_to_reject"])]

        return time_series, stations

    def reject_country(self,
                       time_series: pd.DataFrame,
                       stations: pd.DataFrame
                       ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Reject stations from inputs files as defined by the user"""
        countries_to_reject = self.config["country_to_reject_during_training"]
        names_country_to_reject = stations["name"][stations["country"].isin(countries_to_reject)].values
        time_series = time_series[~time_series["name"].isin(names_country_to_reject)]
        stations = stations[~stations["name"].isin(names_country_to_reject)]
        return time_series, stations

    def _get_stations_test_and_val(self) -> MutableSequence:
        if "space" in self.config["split_strategy_test"] and "space" in self.config["split_strategy_val"]:
            return self.config["stations_test"] + self.config["stations_val"]
        elif "space" in self.config["split_strategy_test"]:
            return self.config["stations_test"]
        elif "space" in self.config["split_strategy_val"]:
            # stations_test or stations_val?
            return self.config["stations_test"]
        else:
            return []

    def _get_train_stations(self,
                            df: pd.DataFrame
                            ) -> List:
        assert "name" in df, "DataFrame must contain a name column"
        all_stations = df["name"].unique()
        stations_test_val = self._get_stations_test_and_val()
        return [s for s in all_stations if s not in set(stations_test_val)]

    def unbalance_training_dataset(self) -> None:
        if self.config["current_variable"] == "T2m":
            raise NotImplementedError("Unbalanced dataset is not implemented for temperature")

        bool_train_labels = self.labels_train["vw10m(m/s)"] >= self.config["unbalanced_threshold"]
        bool_train_labels = bool_train_labels.values

        pos_features = self.inputs_train[bool_train_labels].values
        neg_features = self.inputs_train[~bool_train_labels].values

        pos_labels = self.labels_train[bool_train_labels].values
        neg_labels = self.labels_train[~bool_train_labels].values

        pos_names = self.names_train[bool_train_labels].values
        neg_names = self.names_train[~bool_train_labels].values

        ids = np.arange(len(neg_features))
        choices = np.random.choice(ids, len(pos_features))

        res_neg_features = neg_features[choices]
        res_neg_labels = neg_labels[choices]
        res_neg_names = neg_names[choices]

        assert len(res_neg_features) == len(pos_features)
        assert len(res_neg_labels) == len(pos_labels)
        assert len(res_neg_names) == len(pos_names)

        self.inputs_train = np.concatenate([res_neg_features, pos_features], axis=0)
        self.labels_train = np.concatenate([res_neg_labels, pos_labels], axis=0)
        self.names_train = np.concatenate([res_neg_names, pos_names], axis=0)
        self.length_train = len(self.inputs_train)

    @staticmethod
    def _try_random_choice(list_stations: MutableSequence[str],
                           station: pd.DataFrame,
                           patience: int = 10,
                           stations_to_exclude: MutableSequence = []
                           ) -> MutableSequence[str]:
        i = 0
        while i < patience:
            station_name = np.random.choice(station["name"].values)
            station_already_selected = (station_name in list_stations) or (station_name in stations_to_exclude)
            if station_already_selected:
                print(station_name, patience)
                i += 1
            else:
                list_stations.append(station_name)
                i = patience + 1
        return list_stations

    @staticmethod
    def add_nwp_stats_to_stations(stations: pd.DataFrame,
                                  time_series: pd.DataFrame,
                                  metrics: List[str] = ["rmse"]
                                  ) -> pd.DataFrame:

        for metric in metrics:
            stations[metric] = np.nan
            for station in time_series["name"].unique():
                filter_station = time_series["name"] == station
                time_series_station = time_series.loc[filter_station, ["Wind", "vw10m(m/s)"]].dropna()
                metric_func = get_metric(metric)
                try:
                    mean_metric = metric_func(time_series_station["vw10m(m/s)"].values,
                                              time_series_station["Wind"].values)
                    stations.loc[stations["name"] == station, [metric]] = mean_metric
                except ValueError:
                    print(station)

        return stations

    def add_mode_to_df(self,
                       df: pd.DataFrame
                       ) -> pd.DataFrame:

        assert self.is_prepared

        df["mode"] = np.nan

        filter_test = df["name"].isin(self.get_names("test", unique=True))
        filter_val = df["name"].isin(self.get_names("val", unique=True))
        filter_train = df["name"].isin(self.get_names("train", unique=True))
        filter_other = df["name"].isin(self.get_names("other_countries", unique=True))
        filter_custom = df["name"].isin(self.get_names("custom", unique=True))
        filter_rejected = ~(filter_test | filter_val | filter_train | filter_other | filter_custom)

        df.loc[filter_test, "mode"] = "Test"
        df.loc[filter_val, "mode"] = "Validation"
        df.loc[filter_train, "mode"] = "Training"
        df.loc[filter_other, "mode"] = "other_countries"
        df.loc[filter_rejected, "mode"] = "rejected"
        df.loc[filter_custom, "mode"] = "custom"

        return df

    @staticmethod
    def add_country_to_time_series(time_series: pd.DataFrame,
                                   stations: pd.DataFrame
                                   ) -> pd.DataFrame:
        time_series["country"] = np.nan
        for station in time_series["name"].unique():
            filter_s = stations["name"] == station
            filter_ts = time_series["name"] == station
            time_series.loc[filter_ts, "country"] = stations.loc[filter_s, "country"].values[0]
        return time_series

    @staticmethod
    def add_elevation_category_to_df(df: pd.DataFrame,
                                     list_min: List[int] = [0, 1000, 2000, 3000],
                                     list_max: List[int] = [1000, 2000, 3000, 5000]
                                     ) -> pd.DataFrame:
        df["cat_zs"] = np.nan
        for z_min, z_max in zip(list_min, list_max):
            filter_alti = (z_min <= df["alti"]) & (df["alti"] < z_max)
            df.loc[filter_alti, ["cat_zs"]] = f"{int(z_min)}m $\leq$ Station elevation $<$ {int(z_max)}m"
        return df

    def _select_randomly_test_val_stations(self,
                                           time_series: pd.DataFrame,
                                           stations: pd.DataFrame,
                                           mode: str,
                                           stations_to_exclude: MutableSequence = []):
        metric = self.config["metric_split"]

        stations = self.add_nwp_stats_to_stations(stations, time_series, [metric])

        if mode == "test":
            list_parameters = self.config["parameters_split_test"]
            list_stations = ["Col du Lac Blanc"]
        else:
            list_parameters = self.config["parameters_split_val"]
            list_stations = []

        for parameter in list_parameters:
            print(f"Parameter: {parameter}")
            q33 = np.quantile(stations[parameter].values, 0.33)
            q66 = np.quantile(stations[parameter].values, 0.66)

            small_values = stations[stations[parameter].values <= q33]
            medium_values = stations[(q33 <= stations[parameter].values) & (stations[parameter].values < q66)]
            large_values = stations[q66 <= stations[parameter].values]

            for index, stratified_stations in enumerate([small_values, medium_values, large_values]):
                q33_strat = np.nanquantile(stratified_stations[metric].values, 0.33)
                q66_strat = np.nanquantile(stratified_stations[metric].values, 0.66)

                first_q = stratified_stations[metric] < q33_strat
                second_q = (q33_strat <= stratified_stations[metric]) & (stratified_stations[metric] < q66_strat)
                third_q = q66_strat <= stratified_stations[metric]

                strat_0 = stratified_stations[first_q]
                strat_1 = stratified_stations[second_q]
                strat_2 = stratified_stations[third_q]

                for idx, station in enumerate([strat_0, strat_1, strat_2]):
                    list_stations = self._try_random_choice(list_stations,
                                                            station,
                                                            patience=10,
                                                            stations_to_exclude=stations_to_exclude)

        return list_stations

    def define_test_and_val_stations(self,
                                     time_series: pd.DataFrame,
                                     stations: pd.DataFrame
                                     ) -> None:
        i = 0

        time_series, stations = self.reject_country(time_series, stations)

        self.config["stations_test"] = []
        self.config["stations_val"] = []
        col_du_lac_blanc_not_in_test = "Col du Lac Blanc" not in self.config["stations_test"]
        while col_du_lac_blanc_not_in_test:
            i += 1
            self.config["stations_test"] = self._select_randomly_test_val_stations(time_series,
                                                                                   stations,
                                                                                   mode="test")
            self.config["stations_val"] = self._select_randomly_test_val_stations(time_series,
                                                                                  stations,
                                                                                  mode="val",
                                                                                  stations_to_exclude=self.config[
                                                                                      "stations_test"])

            col_du_lac_blanc_not_in_test = "Col du Lac Blanc" not in self.config["stations_test"]

    def _apply_quick_test(self,
                          time_series: pd.DataFrame
                          ) -> pd.DataFrame:
        return time_series[time_series["name"].isin(self.config["quick_test_stations"])]

    def prepare_custom_devine_data(self,
                                   custom_time_series: pd.DataFrame,
                                   dict_topo_custom: dict
                                   ):

        self.inputs_custom = custom_time_series
        self.length_custom = len(self.inputs_custom)
        self.names_custom = ["custom" for i in range(self.length_custom)]
        self.dict_topos = dict_topo_custom
        self._set_is_prepared()

    @staticmethod
    def add_month_and_hour_to_time_series(time_series: pd.DataFrame
                                          ) -> pd.DataFrame:
        time_series["month"] = time_series.index.month
        time_series["hour"] = time_series.index.hour
        return time_series

    def remove_null_speeds_time_series(self, time_series, threshold=None):
        if threshold is None:
            threshold = self.config["threshold_null_speed"]
        filter_model = time_series["Wind"] > threshold
        filter_obs = time_series['vw10m(m/s)'] > threshold
        return time_series[filter_model & filter_obs]

    @staticmethod
    def generate_random_idx(time_series: pd.DataFrame, min_: int = -25, max_: int = 25) -> pd.DataFrame:
        time_series["idx_x"] = np.random.randint(min_, max_ + 1, size=len(time_series))
        time_series["idx_y"] = np.random.randint(min_, max_ + 1, size=len(time_series))
        return time_series

    def prepare_train_test_data(self,
                                _shuffle: bool = True,
                                variables_needed: bool = None):

        # Pre-processing time_series
        time_series = self.loader.load_time_series_pkl()
        stations = self.loader.load_stations_pkl()

        # Remove null wind speed (to fit direction, which is not defined for null speeds)
        if self.config.get("remove_null_speeds", False):
            print("\nRemoved null speeds.\n")
            time_series = self.remove_null_speeds_time_series(time_series)

        # Reject stations
        time_series, stations = self.reject_stations(time_series, stations)

        # Quick test
        if self.config["quick_test"]:
            time_series = self._apply_quick_test(time_series)

        # Add topo characteristics
        time_series = self.add_topo_carac_time_series(time_series, stations)
        time_series = self.add_topographic_parameters_llt(time_series)

        # Add country
        time_series = self.add_country_to_time_series(time_series, stations)

        # Add month and hour
        if "month" in self.variables_needed or "hour" in self.variables_needed:
            time_series = self.add_month_and_hour_to_time_series(time_series)

        # Random idx for uncentered training
        if self.config.get("random_idx", False):
            time_series = self.generate_random_idx(time_series)

        # Wind fields to wind components
        if (['U_obs'] in self.config["labels"]) or ('V_obs' in self.config["labels"]):
            time_series['U_obs'], time_series['V_obs'] = wind2comp(time_series['vw10m(m/s)'],
                                                                   time_series['winddir(deg)'],
                                                                   unit_direction="degree")

        # Select variables
        time_series = self._select_all_variables_needed(time_series, variables_needed)

        # Define test/train/val stations if random
        if self.config["stations_test"] == "random" and self.config["stations_val"] == "random":
            self.define_test_and_val_stations(time_series, stations)

        # Dropna
        time_series = time_series.dropna()

        # Shuffle
        if self.config.get("shuffle", True):
            time_series = shuffle(time_series)

        # Split time_series with countries
        if self.config.get("country_to_reject_during_training", False):
            time_series, time_series_other_countries = self.splitter.split_wrapper(time_series,
                                                                                   stations=stations,
                                                                                   split_strategy="country")

        # Stations train
        self.config[f"stations_train"] = self._get_train_stations(time_series)

        # train/test split
        split_strategy = "random" if self.config[f"quick_test"] else None
        time_series_train, time_series_test, time_series_val = self.splitter.split_train_test_val(time_series,
                                                                                                  split_strategy=split_strategy)
        # Other countries
        if self.config.get("country_to_reject_during_training", False):
            _, time_series_other_countries = self.splitter.split_wrapper(time_series_other_countries,
                                                                         mode="test",
                                                                         split_strategy="time")

        # Input variables
        self.inputs_train = time_series_train[self.config["input_variables"]]
        self.inputs_test = time_series_test[self.config["input_variables"]]
        if self.config["stations_val"]:
            self.inputs_val = time_series_val[self.config["input_variables"]]
        if self.config.get("country_to_reject_during_training", False):
            self.inputs_other_countries = time_series_other_countries[self.config["input_variables"]]

        # Length
        self.length_train = len(self.inputs_train)
        self.length_test = len(self.inputs_test)
        if self.config["stations_val"]:
            self.length_val = len(self.inputs_val)
        if self.config.get("country_to_reject_during_training", False):
            self.length_other_countries = len(self.inputs_other_countries)

        # labels
        self.labels_train = time_series_train[self.config["labels"]]
        self.labels_test = time_series_test[self.config["labels"]]
        if self.config["stations_val"]:
            self.labels_val = time_series_val[self.config["labels"]]
        if self.config.get("country_to_reject_during_training", False):
            self.labels_other_countries = time_series_other_countries[self.config["labels"]]

        # names
        self.names_train = time_series_train["name"]
        self.names_test = time_series_test["name"]
        if self.config["stations_val"]:
            self.names_val = time_series_val["name"]
        if self.config.get("country_to_reject_during_training", False):
            self.names_other_countries = time_series_other_countries["name"]

        # idx_x and idx_y
        if self.config.get("random_idx", False):
            self.idx_x_train = time_series_train["idx_x"]
            self.idx_y_train = time_series_train["idx_y"]
            self.idx_x_test = time_series_test["idx_x"]
            self.idx_y_test = time_series_test["idx_y"]
            if self.config["stations_val"]:
                self.idx_x_val = time_series_val["idx_x"]
                self.idx_y_val = time_series_val["idx_y"]
            if self.config.get("country_to_reject_during_training", False):
                self.idx_x_other_countries = time_series_other_countries["idx_x"]
                self.idx_y_other_countries = time_series_other_countries["idx_y"]

        if self.config.get("standardize", True):
            self.mean_standardize = self.inputs_train.mean()
            self.std_standardize = self.inputs_train.std()

        if self.config.get("unbalanced_dataset", False):
            self.unbalance_training_dataset()

        self._set_is_prepared()

    def get_inputs(self,
                   mode: str
                   ) -> Union[pd.Series, pd.DataFrame]:
        return getattr(self, f"inputs_{mode}")

    def get_length(self,
                   mode: str
                   ) -> float:
        return getattr(self, f"length_{mode}")

    def get_labels(self,
                   mode: str
                   ) -> pd.DataFrame:
        return getattr(self, f"labels_{mode}")

    def get_names(self,
                  mode: str,
                  unique: bool = False
                  ) -> MutableSequence:
        names = getattr(self, f"names_{mode}")

        if unique:
            return list(names.unique())
        else:
            return names

    def get_idx(self, mode: str):
        return getattr(self, f"idx_x_{mode}"), getattr(self, f"idx_y_{mode}")

    def get_mean(self) -> MutableSequence[float]:
        return self.mean_standardize

    def get_std(self) -> MutableSequence[float]:
        return self.std_standardize

    def get_tf_uncentered_topos(self,
                                mode: Union[str, None] = None,
                                names: Union[MutableSequence[str], None] = None,
                                idx_x: Union[MutableSequence[str], None] = None,
                                idx_y: Union[MutableSequence[str], None] = None,
                                ) -> tf.data.Dataset:

        output_shapes = (140, 140, 1)

        if names is None:
            names = self.get_names(mode)

        if (idx_x is None) and (idx_y is None):
            idx_x, idx_y = self.get_idx(mode)

        if hasattr(names, "values"):
            names = names.values

        if hasattr(idx_x, "values"):
            idx_x = idx_x.values

        if hasattr(idx_y, "values"):
            idx_y = idx_y.values

        topos_generator = MapGeneratorUncentered(names, idx_x=idx_x, idx_y=idx_y, config=self.config)

        return tf.data.Dataset.from_generator(topos_generator, output_types=tf.float32, output_shapes=output_shapes)

    def get_tf_map(self,
                   names_map: MutableSequence,
                   mode: str,
                   names: Union[MutableSequence[str], None] = None,
                   output_shapes: MutableSequence = [140, 140, 1],
                   ) -> tf.data.Dataset:

        output_shapes[2] = len(self.config["map_variables"])

        if names is None:
            names = self.get_names(mode)

        if self.config.get("custom_dataloader", False):
            generator = MapGeneratorCustom(names, self.dict_topos)
        else:
            generator = MapGenerator(names_map, names, self.config)

        return tf.data.Dataset.from_generator(generator, output_types=tf.float32, output_shapes=output_shapes)

    def get_tf_mean_std(self,
                        mode: str
                        ) -> Tuple[tf.data.Dataset, tf.data.Dataset]:
        length = self.get_length(mode)
        mean = self.get_mean()
        std = self.get_std()

        mean = tf.data.Dataset.from_generator(MeanGenerator(mean,
                                                            length),
                                              output_types=tf.float32,
                                              output_shapes=(self.config["nb_input_variables"],))
        std = tf.data.Dataset.from_generator(MeanGenerator(std,
                                                           length),
                                             output_types=tf.float32,
                                             output_shapes=(self.config["nb_input_variables"],))
        return mean, std

    def get_tf_map_inputs(self,
                          mode: str = "test",
                          names: MutableSequence["str"] = None,
                          output_shapes: MutableSequence = [140, 140, 1],
                          uncentered: bool = False,
                          idx_x: MutableSequence[float] = None,
                          idx_y: MutableSequence[float] = None
                          ):
        if uncentered:
            return self.get_tf_uncentered_topos(mode=mode,
                                                names=names,
                                                idx_x=idx_x,
                                                idx_y=idx_y)
        else:
            output_shapes[2] = len(self.config["map_variables"])
            return self.get_tf_map(names_map=self.config["map_variables"],
                                   mode=mode,
                                   names=names,
                                   output_shapes=output_shapes)

    def get_tf_zipped_inputs(self,
                             mode: str = "test",
                             inputs: Union[pd.Series, pd.DataFrame, None] = None,
                             names: MutableSequence["str"] = None,
                             output_shapes: MutableSequence = [140, 140, 1]
                             ) -> tf.data.Dataset:

        output_shapes[2] = len(self.config["map_variables"])

        if inputs is None:
            inputs = self.get_inputs(mode)

        if hasattr(inputs, "values"):
            inputs = inputs.values

        inputs = tf.data.Dataset.from_tensor_slices(inputs)

        if self.config.get("random_idx", False):
            uncentered = True
        else:
            uncentered = False

        if self.config["standardize"]:
            mean, std = self.get_tf_mean_std(mode)
            return tf.data.Dataset.zip((self.get_tf_map_inputs(mode=mode,
                                                               names=names,
                                                               output_shapes=output_shapes,
                                                               uncentered=uncentered),
                                        inputs,
                                        mean,
                                        std))
        else:
            return tf.data.Dataset.zip((self.get_tf_map_inputs(mode=mode,
                                                               names=names,
                                                               output_shapes=output_shapes,
                                                               uncentered=uncentered),
                                        inputs))

    def _get_all_zipped(self,
                        mode: str
                        ) -> tf.data.Dataset:
        labels = self.get_labels(mode)

        if hasattr(labels, "values"):
            labels = labels.values

        labels = tf.data.Dataset.from_tensor_slices(labels)

        inputs = self.get_inputs(mode)

        if hasattr(inputs, "values"):
            inputs = inputs.values

        inputs = tf.data.Dataset.from_tensor_slices(inputs)

        if self.config["standardize"]:
            mean, std = self.get_tf_mean_std(mode)
            return tf.data.Dataset.zip((self.get_tf_map(names_map=["topos"], mode=mode),
                                        inputs,
                                        mean,
                                        std,
                                        labels))
        else:
            return tf.data.Dataset.zip((self.get_tf_map(names_map=["topos"], mode=mode),
                                        inputs,
                                        labels))

    def get_tf_zipped_inputs_labels(self,
                                    mode: str,
                                    inputs: Union[pd.Series, pd.DataFrame] = None,
                                    names: MutableSequence["str"] = None,
                                    output_shapes: MutableSequence = [140, 140, 1],
                                    labels: Union[pd.Series, pd.DataFrame] = None
                                    ) -> tf.data.Dataset:
        if labels is None:
            labels = self.get_labels(mode)

        if hasattr(labels, "values"):
            labels = labels.values

        output_shapes[2] = len(self.config["map_variables"])

        labels = tf.data.Dataset.from_tensor_slices(labels)
        inputs = self.get_tf_zipped_inputs(mode=mode, inputs=inputs, names=names, output_shapes=output_shapes)
        return tf.data.Dataset.zip((inputs, labels))

    def get_time_series(self,
                        prepared: bool = False,
                        mode: bool = True
                        ) -> pd.DataFrame:
        time_series = self.loader.load_time_series_pkl()
        if prepared:

            assert self.is_prepared

            stations = self.get_stations()

            # Reject stations
            time_series, stations = self.reject_stations(time_series, stations)

            # Add topo characteristics
            time_series = self.add_topo_carac_time_series(time_series, stations)
            time_series = self.add_topographic_parameters_llt(time_series)

            # Add country
            time_series = self.add_country_to_time_series(time_series, stations)

            # Add mode
            if mode:
                time_series = self.add_mode_to_df(time_series)

            # Select variables
            time_series = self._select_all_variables_needed(time_series)

            time_series = time_series.dropna()

            return time_series
        else:
            return time_series

    def get_stations(self,
                     add_mode: Optional[bool] = False
                     ) -> pd.DataFrame:
        stations = self.loader.load_stations_pkl()
        if add_mode:
            stations = self.add_mode_to_df(stations)
        return stations

    def get_predictions(self,
                        mode: str):
        try:
            return getattr(self, f"predicted_{mode}")
        except AttributeError:
            try:
                return getattr(self, f"predicted{mode}")
            except AttributeError:
                raise NotImplementedError("We only support modes train/test/val/other_countries/devine")

    def get_topos(self,
                  mode: Union[str, None] = None,
                  names: Union[MutableSequence[str], None] = None
                  ) -> Generator:
        if names is None:
            names = self.get_names(mode)

        if hasattr(names, "values"):
            names = names.values

        topos_generator = MapGenerator(["topos"], names, self.config)

        return topos_generator()

    def get_batched_inputs_labels(self,
                                  mode: str,
                                  inputs: Union[pd.Series, pd.DataFrame] = None,
                                  names: MutableSequence["str"] = None,
                                  output_shapes: MutableSequence = [140, 140, 1],
                                  labels: Union[pd.Series, pd.DataFrame] = None
                                  ) -> DatasetV2:

        output_shapes[2] = len(self.config["map_variables"])
        dataset = self.get_tf_zipped_inputs_labels(mode,
                                                   inputs=inputs,
                                                   names=names,
                                                   output_shapes=output_shapes,
                                                   labels=labels)
        batch_func = {"train": self.batcher.batch_train,
                      "test": self.batcher.batch_test,
                      "val": self.batcher.batch_val}

        return batch_func[mode](dataset)

    def set_predictions(self,
                        results: MutableSequence[float],
                        mode: str = "test",
                        str_model: str = "_nn"
                        ) -> None:
        names = self.get_names(mode)
        df, mode_str = self.results_setter.prepare_df_results(results, names, mode=mode, str_model=str_model)
        setattr(self, f"predicted_{mode_str}", df)

        if self.config.get("get_intermediate_output", False):
            df, _ = self.results_setter.prepare_df_results(results, names, mode=mode, str_model="_int")
            setattr(self, f"predicted_int", df)

    def _set_is_prepared(self) -> None:
        self.is_prepared = True

    def add_model(self,
                  model: str,
                  mode: str = "test"
                  ) -> None:

        path_to_files = {"UV":
                             {"_D": self.config["path_to_devine"] + f"devine_2022_10_25_speed_{mode}.pkl",
                              "_A": self.config["path_to_analysis"] + "time_series_bc_a.pkl",
                              "_DA": self.config[
                                         "path_to_devine"] + f"devine_arome_analysis_2023_03_16_output_speed_{mode}.pkl"
                              },
                         "UV_DIR":
                             {"_D": self.config["path_to_devine"] + f"devine_2022_08_04_v4_{mode}_dir.pkl",
                              "_A": self.config["path_to_analysis"] + "time_series_bc_a.pkl",
                              "_DA": self.config[
                                         "path_to_devine"] + f"devine_arome_analysis_2023_03_16_output_direction_{mode}.pkl"
                              }
                         }

        predictions = pd.read_pickle(path_to_files[self.config["current_variable"]][model])

        if model == "_A":
            predictions = predictions.rename(columns={"Wind": "UV_A"})
            predictions = predictions.rename(columns={"Wind_DIR": "UV_DIR_A"})

        if model == "_DA":
            predictions = predictions.rename(columns={"UV_D": "UV_DA"})
            predictions = predictions.rename(columns={"UV_DIR_D": "UV_DIR_DA"})

        setattr(self, f"predicted{model}", predictions)
