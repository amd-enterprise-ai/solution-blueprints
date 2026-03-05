# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import logging
from typing import Dict, Optional, Protocol


class LogProtocol(Protocol):
    def verbose(self, msg: str) -> None:
        pass

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def train(self, msg: str) -> None:
        pass

    def eval(self, msg: str) -> None:
        pass

    def warn(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass

    def fatal(self, msg: str) -> None:
        pass

    def exception(self, msg: str) -> None:
        pass


class CustomLogger:
    """
    Lightweight logger wrapper with extended log levels.
    """

    _DEFAULT_NAME = "AIComponents"

    def __init__(self, name: Optional[str] = None) -> None:
        self._logger_name = name or self._DEFAULT_NAME
        self._logger = logging.getLogger(self._logger_name)

        self._level_map: Dict[str, int] = self._build_levels()
        self._register_levels()
        self._configure_output()

        self.verbose = self._create_log_method("VERBOSE")
        self.debug = self._create_log_method("DEBUG")
        self.info = self._create_log_method("INFO")
        self.train = self._create_log_method("TRAIN")
        self.eval = self._create_log_method("EVAL")
        self.warn = self._create_log_method("WARN")
        self.error = self._create_log_method("ERROR")
        self.fatal = self._create_log_method("FATAL")
        self.exception = self._logger.exception

    def _create_log_method(self, level_name: str):
        level_value = self._level_map[level_name]

        def log_method(msg: str) -> None:
            self._logger.log(level_value, msg)

        return log_method

    # ------------------------------------------------------------------ #
    # Initialization helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_levels() -> Dict[str, int]:
        base_levels = {
            "VERBOSE": 15,
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "ERROR": logging.ERROR,
            "FATAL": logging.CRITICAL,
            "EXCEPTION": 90,
        }

        custom_offset = 5
        base_debug = logging.DEBUG
        base_levels.update(
            {
                "TRAIN": base_debug + custom_offset,
                "EVAL": base_debug + custom_offset * 2,
                "WARN": base_debug + custom_offset * 3,
            }
        )
        return base_levels

    def _register_levels(self) -> None:
        for label, value in self._level_map.items():
            logging.addLevelName(value, label)

    def _make_logger(self, level: int):
        def _log(message: str) -> None:
            self._logger.log(level, message)

        return _log

    def _configure_output(self) -> None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", "%H:%M:%S"))

        self._disable_propagation()
        self._set_base_level()
        self._logger.addHandler(handler)

    def _disable_propagation(self):
        self._logger.propagate = False

    def _set_base_level(self):
        self._logger.setLevel(logging.INFO)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def configure_level(self, level: str) -> None:
        level_key = level.upper()
        if level_key in self._level_map:
            self._logger.setLevel(self._level_map[level_key])
        else:
            self._logger.setLevel(getattr(logging, level_key, logging.INFO))

    def shutdown(self) -> None:
        for handler in list(self._logger.handlers):
            handler.close()
            self._logger.removeHandler(handler)
