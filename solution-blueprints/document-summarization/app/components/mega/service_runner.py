# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import Any, Callable, Dict, Optional, Type

import uvicorn
from fastapi import FastAPI

from ..models.documents import TextDoc


class ServiceRunner:
    def __init__(
        self,
        host: Optional[str] = "localhost",
        name: str = "",
        endpoint: Optional[str] = "/",
        port: Optional[int] = 8080,
        request_schema: Type[Any] | None = TextDoc,  # Schema for input data
        response_schema: Type[Any] | None = TextDoc,  # Schema for output data
        cert_path: str | None = None,  # Path to SSL certificate
        key_path: str | None = None,  # Path to private key
        service_info: str | None = None,  # Service description text
    ) -> None:
        self.name = name or self.__class__.__name__
        self.host = host
        self.input_datatype = request_schema or TextDoc  # fallback
        self.output_datatype = response_schema or TextDoc
        self.host = host or "localhost"
        self.endpoint = endpoint or "/"
        self.port = port or 8080

        self.app = FastAPI(title=self.name, description=service_info)
        self._ssl_kwargs: dict[str, Any] = {}
        self.ssl_config: Dict[str, Any] = {}
        if key_path:
            self.ssl_config["ssl_keyfile"] = key_path
        if cert_path:
            self.ssl_config["ssl_certfile"] = cert_path

    def add_route(self, path: str, handler: Callable[..., Any], methods: list[str]) -> None:
        self.app.add_api_route(path, handler, methods=methods)

    def start(self) -> None:
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            **self._ssl_kwargs,
        )
