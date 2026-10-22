"""The MCP server: JSON-RPC over streamable HTTP, without a stream. Each POST gets one JSON answer,
which the spec allows, so the server works behind the WSGI app with no extra process."""

import json

from . import tools

PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = """Tools for Piston Cup Paddock, an Assetto Corsa league app (leagues, championships,
seasons, rounds, results, votes, drivers, accounts, telemetry, and the server collector).
Each call runs as the signed-in person, with that person's permissions, and the app audit log
records each change under that name.
Start with overview to see the championships and seasons. Use search_operations to find the
API path, its parameters, and its body, then api_read (GET) or api_write (POST, PUT, PATCH,
DELETE). IDs are not guessable: read them first. Before a change that deletes or replaces data,
say what will change and ask the person to confirm."""

OPEN = {"readOnlyHint": True, "openWorldHint": False}

TOOLS = [
    {
        "name": "overview",
        "title": "Overview",
        "description": (
            "Who you are in the app, and the championships and seasons that you can see, "
            "with their IDs."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": OPEN,
    },
    {
        "name": "search_operations",
        "title": "Find an API operation",
        "description": (
            "Find app API operations by words, for example 'season entries', 'ballot open', "
            "'round calendar', 'delete', 'accounts'. Gives the method, the path, the parameters, "
            "and the JSON body of each match."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words about the task"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "required": ["query"],
        },
        "annotations": OPEN,
    },
    {
        "name": "api_read",
        "title": "Read from the app",
        "description": (
            "Run a GET operation of the app API, for example /api/seasons/12. Changes nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The API path with the IDs, from search_operations",
                },
                "query": {
                    "type": "object",
                    "description": "Query parameters",
                    "additionalProperties": True,
                },
            },
            "required": ["path"],
        },
        "annotations": OPEN,
    },
    {
        "name": "api_write",
        "title": "Change the app",
        "description": (
            "Run a POST, PUT, PATCH, or DELETE operation of the app API. It changes data, as "
            "the signed-in person. Check the body with search_operations first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["POST", "PUT", "PATCH", "DELETE"]},
                "path": {"type": "string", "description": "The API path with the IDs"},
                "query": {"type": "object", "additionalProperties": True},
                "body": {"description": "The JSON body of the operation"},
            },
            "required": ["method", "path"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    },
]


def _text(data, error: bool = False) -> dict:
    return {
        "content": [
            {"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=1, default=str)}
        ],
        "isError": error,
    }


def call_tool(user, name: str, arguments: dict) -> dict:
    try:
        if name == "overview":
            return _text(tools.overview(user))
        if name == "search_operations":
            found = tools.search(str(arguments.get("query", "")), int(arguments.get("limit", 8)))
            return _text(found or "No operation matches. Try other words.")
        if name == "api_read":
            result = tools.call(user, "GET", str(arguments.get("path", "")), arguments.get("query"))
            return _text(result, result["status"] >= 400)
        if name == "api_write":
            method = str(arguments.get("method", "")).upper()
            if method not in ("POST", "PUT", "PATCH", "DELETE"):
                return _text("Use POST, PUT, PATCH, or DELETE. For GET, use api_read.", True)
            result = tools.call(
                user,
                method,
                str(arguments.get("path", "")),
                arguments.get("query"),
                arguments.get("body"),
            )
            return _text(result, result["status"] >= 400)
    except tools.ToolError as error:
        return _text(str(error), True)
    return _text(f"Unknown tool: {name}", True)


def _result(id_, result) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(user, message: dict) -> dict | None:
    """One JSON-RPC message. A notification gets no answer (None)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid request")
    method = message.get("method")
    id_ = message.get("id")
    params = message.get("params") or {}
    if id_ is None:
        return None  # notifications/initialized and the other notifications
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(
            id_,
            {
                "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "piston-cup-paddock",
                    "title": "Piston Cup Paddock",
                    "version": "1.0.0",
                },
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": TOOLS})
    if method == "tools/call":
        return _result(
            id_, call_tool(user, str(params.get("name", "")), params.get("arguments") or {})
        )
    return _error(id_, -32601, f"Method not found: {method}")
