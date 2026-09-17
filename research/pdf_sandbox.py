"""OS confinement for untrusted PDF parsing; no service credentials are forwarded."""

import json
import os
import shutil
import sys
from pathlib import Path

from django.conf import settings


class SandboxUnavailable(RuntimeError):
    pass


def parser_command(directory):
    parser = Path(__file__).with_name("pdf_extract.py").resolve()
    runtime = list(dict.fromkeys(str(Path(p).resolve()) for p in (sys.prefix, sys.base_prefix)))
    command = [sys.executable, "-I", str(parser)]
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists():
        reads = runtime + [
            "/System",
            "/usr/lib",
            "/usr/share",
            "/Library/Apple",
            "/private/preboot/Cryptexes",
        ]
        profile = "(version 1)(deny default)(allow process-exec)(allow signal (target self))"
        profile += "(allow sysctl-read)"
        profile += (
            '(allow mach-lookup (global-name "com.apple.system.notification_center") '
            '(global-name "com.apple.logd"))'
        )
        profile += '(allow file-read-metadata)(allow file-read* file-write* (literal "/dev/null"))'
        profile += (
            "(allow file-read* "
            + " ".join(f"(subpath {json.dumps(path)})" for path in reads)
            + f' (literal {json.dumps(str(parser))}) (literal "/dev/urandom") (literal "/"))'
        )
        return ["/usr/bin/sandbox-exec", "-p", profile, *command], "sandbox-exec"
    if sys.platform == "linux" and (bubblewrap := shutil.which("bwrap")):
        args = [bubblewrap, "--unshare-all", "--die-with-parent", "--new-session"]
        for path in dict.fromkeys(["/usr", "/lib", "/lib64", *runtime]):
            if Path(path).exists():
                args.extend(["--ro-bind", path, path])
        args.extend(
            [
                "--ro-bind",
                str(parser),
                str(parser),
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--chdir",
                "/tmp",
                *command,
            ]
        )
        return args, "bubblewrap"
    if settings.DEBUG and os.environ.get("RESEARCH_PDF_ALLOW_UNSANDBOXED_LOCAL") == "1":
        return command, "explicit-local-fallback"
    raise SandboxUnavailable("PDF extraction needs sandbox-exec (macOS) or bubblewrap (Linux).")


def parser_environment(directory):
    return {"LANG": "C.UTF-8", "HOME": directory, "TMPDIR": directory}
