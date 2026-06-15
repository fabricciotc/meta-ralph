from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, fn: Callable, schema: Dict[str, Any] | None = None) -> None:
        self._tools[name] = fn
        self._schemas[name] = schema or self._infer_schema(name, fn)

    def _infer_schema(self, name: str, fn: Callable) -> Dict[str, Any]:
        sig = inspect.signature(fn)
        doc = inspect.getdoc(fn) or ""
        params = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            params.append(
                {
                    "name": pname,
                    "type": str(param.annotation) if param.annotation is not param.empty else "str",
                    "required": param.default is param.empty,
                }
            )
        return {"name": name, "description": doc, "parameters": params}

    def get(self, name: str) -> Callable:
        return self._tools[name]

    def get_schema(self, name: str) -> Dict[str, Any]:
        return self._schemas[name]

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def list(self) -> List[Dict[str, Any]]:
        return [self._schemas[name] for name in self.list_names()]

    def invoke(self, name: str, params: Dict[str, Any]) -> Any:
        fn = self._tools[name]
        return fn(**params)
