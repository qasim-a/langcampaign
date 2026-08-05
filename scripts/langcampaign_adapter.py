#!/usr/bin/env python3
"""Platform-neutral process entry point for the bundled LangCampaign engine."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _fail(message: str) -> int:
    _emit({
        "success": False,
        "error": {
            "code": "UNSUPPORTED_ENVIRONMENT",
            "message": message,
            "retryable": False,
        },
    })
    return 3


def _bundled_src(script_file: Path) -> Path:
    root = script_file.resolve().parents[1]
    if not (root / ".codex-plugin" / "plugin.json").is_file():
        raise RuntimeError("plugin manifest is missing")
    package = root / "src" / "langcampaign" / "__init__.py"
    if not package.is_file():
        raise RuntimeError("bundled LangCampaign package is missing")
    return root / "src"


def install_probe(script_file: Path | None = None) -> int:
    if sys.version_info < (3, 11):
        return _fail("Python 3.11 or newer is required")
    try:
        bundled_src = _bundled_src(script_file or Path(__file__))
        sys.path.insert(0, str(bundled_src))
        for name in tuple(sys.modules):
            if name == "langcampaign" or name.startswith("langcampaign."):
                del sys.modules[name]
        import langcampaign
        from langcampaign.profile import load_or_create_profile, resolve_data_root

        package_path = Path(langcampaign.__file__).resolve()
        if not package_path.is_relative_to(bundled_src.resolve()):
            raise RuntimeError("bundled LangCampaign package could not be selected")
        override = os.environ.get("LANGCAMPAIGN_DATA_ROOT")
        data_root = Path(override) if override else resolve_data_root()
        profile = load_or_create_profile(data_root)
        manifest = json.loads((bundled_src.parent / ".codex-plugin/plugin.json").read_text())
    except RuntimeError as error:
        return _fail(str(error))
    except Exception:
        return _fail("LangCampaign personal storage is unavailable")
    _emit({
        "success": True,
        "data": {
            "python_compatible": True,
            "plugin_version": manifest["version"],
            "profile_ready": True,
            "learner_id": profile.learner_id,
            "package_path": str(package_path),
            "data_root": str(data_root),
        },
    })
    return 0


def run_protocol(script_file: Path | None = None) -> int:
    operation_id = None
    try:
        bundled_src = _bundled_src(script_file or Path(__file__))
        sys.path.insert(0, str(bundled_src))
        for name in tuple(sys.modules):
            if name == "langcampaign" or name.startswith("langcampaign."):
                del sys.modules[name]
        from langcampaign.profile import ProfileError, UnsupportedProfileVersionError, load_or_create_profile, resolve_data_root
        from langcampaign.protocol import decode_request, dispatch, encode_response, failure_response, ProtocolError, ProtocolErrorCode
        from langcampaign.receipts import execute_idempotent

        request = decode_request(sys.stdin.buffer.read(1024 * 1024 + 1))
        operation_id = request.operation_id
        override = os.environ.get("LANGCAMPAIGN_DATA_ROOT")
        data_root = Path(override) if override else resolve_data_root()
        try:
            profile = load_or_create_profile(data_root)
        except UnsupportedProfileVersionError as profile_error:
            error = ProtocolError(
                ProtocolErrorCode.UNSUPPORTED_SCHEMA,
                str(profile_error),
            )
            sys.stdout.buffer.write(encode_response(failure_response(error, operation_id)))
            return 2
        except (OSError, ProfileError):
            error = ProtocolError(
                ProtocolErrorCode.PERSISTENCE_FAILURE,
                "LangCampaign personal storage is unavailable",
                retryable=True,
            )
            sys.stdout.buffer.write(encode_response(failure_response(error, operation_id)))
            return 4
        if request.mutation:
            response = execute_idempotent(
                data_root,
                request.operation_id,
                request.operation.value,
                request.input,
                lambda: dispatch(request, data_root / "learners", profile.learner_id),
            )
        else:
            response = dispatch(request, data_root / "learners", profile.learner_id)
        sys.stdout.buffer.write(encode_response(response))
        return 0
    except ProtocolError as error:
        sys.stdout.buffer.write(encode_response(failure_response(error, operation_id)))
        return 2
    except RuntimeError as error:
        return _fail(str(error))
    except Exception:
        from langcampaign.protocol import ProtocolError, ProtocolErrorCode, encode_response, failure_response
        error = ProtocolError(ProtocolErrorCode.INTERNAL_ERROR, "unexpected internal error")
        sys.stdout.buffer.write(encode_response(failure_response(error, operation_id)))
        return 70


if __name__ == "__main__":
    raise SystemExit(run_protocol())
