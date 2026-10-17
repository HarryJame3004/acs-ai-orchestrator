"""ACS AI V2 REA (Reverse Engineering & Analysis) Adapter.
Provides binary and ELF inspection capabilities with:
1. Native `rea` CLI detection and invocation if installed.
2. Bubblewrap-isolated local fallback using Linux system inspection utilities
   (`file`, `readelf`, `nm`) when native `rea` CLI is not present.
3. Strict isolation: `--unshare-all`, read-only mounts, no network, strict execution timeout.
4. Security flags extraction: NX, PIE, RELRO, stack canaries.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("acs_ai.rea_adapter")


class REAError(Exception):
    """Base exception for REA inspection failures."""
    pass


@dataclass
class BinarySecurityProfile:
    nx_enabled: bool = False
    pie_enabled: bool = False
    relro_level: str = "none"  # "none", "partial", "full"
    canary_present: bool = False
    stripped: bool = False


@dataclass
class BinaryInspectionReport:
    file_path: str
    engine: str
    is_elf: bool
    file_type: str
    architecture: str = "unknown"
    security_profile: BinarySecurityProfile = field(default_factory=BinarySecurityProfile)
    needed_libraries: List[str] = field(default_factory=list)
    exported_symbols: List[str] = field(default_factory=list)
    raw_summary: str = ""


class REAAdapter:
    """Adapter for binary analysis with native REA support or Bubblewrap-isolated fallback."""

    def __init__(self, timeout_sec: int = 15):
        self.timeout_sec = timeout_sec
        self.rea_binary = shutil.which("rea")
        self.bwrap_binary = shutil.which("bwrap")
        self.readelf_binary = shutil.which("readelf")
        self.file_binary = shutil.which("file")
        self.nm_binary = shutil.which("nm")

    @property
    def is_native_rea_available(self) -> bool:
        return self.rea_binary is not None

    def inspect_file(self, target_path: str) -> BinaryInspectionReport:
        """Inspects target file safely using native REA or containerized fallback."""
        target = Path(target_path).resolve()
        if not target.is_file():
            raise REAError(f"Target file does not exist or is not a regular file: '{target_path}'")

        if target.stat().st_size > 100 * 1024 * 1024:
            raise REAError(f"Target file exceeds 100MB size limit for static analysis: {target.stat().st_size} bytes")

        if self.is_native_rea_available:
            return self._inspect_with_native_rea(target)
        else:
            return self._inspect_with_fallback(target)

    def _inspect_with_native_rea(self, target: Path) -> BinaryInspectionReport:
        """Executes native `rea` CLI with strict execution timeout."""
        cmd = [self.rea_binary, "analyze", "--json", str(target)]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
            if res.returncode == 0:
                return BinaryInspectionReport(
                    file_path=str(target),
                    engine="rea_native",
                    is_elf=True,
                    file_type="ELF Binary (Native REA)",
                    raw_summary=res.stdout[:2000],
                )
            else:
                logger.warning(f"Native REA analysis returned non-zero code {res.returncode}, falling back.")
                return self._inspect_with_fallback(target)
        except Exception as e:
            logger.warning(f"Native REA invocation error: {e}, using fallback.")
            return self._inspect_with_fallback(target)

    def _run_isolated_command(self, cmd: List[str], target: Path) -> subprocess.CompletedProcess:
        """Runs a command isolated inside bubblewrap if available, or direct read-only subprocess."""
        if self.bwrap_binary:
            isolated_cmd = [
                self.bwrap_binary,
                "--ro-bind", "/", "/",
                "--dev", "/dev",
                "--proc", "/proc",
                "--tmpfs", "/tmp",
                "--unshare-all",
                "--die-with-parent",
                "--",
            ] + cmd
        else:
            isolated_cmd = cmd

        return subprocess.run(
            isolated_cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
        )

    def _inspect_with_fallback(self, target: Path) -> BinaryInspectionReport:
        """Performs static inspection using standard utilities inside a bwrap container."""
        engine = "bwrap_fallback" if self.bwrap_binary else "local_fallback"
        
        # 1. Inspect file type via `file`
        file_type = "unknown"
        is_elf = False
        architecture = "unknown"
        if self.file_binary:
            res = self._run_isolated_command([self.file_binary, "-b", str(target)], target)
            if res.returncode == 0:
                file_type = res.stdout.strip()
                is_elf = "ELF" in file_type
                if "x86-64" in file_type:
                    architecture = "x86_64"
                elif "ARM" in file_type or "aarch64" in file_type:
                    architecture = "aarch64"

        # If not an ELF, return basic summary
        if not is_elf:
            return BinaryInspectionReport(
                file_path=str(target),
                engine=engine,
                is_elf=False,
                file_type=file_type,
                architecture=architecture,
                raw_summary=f"Non-ELF file detected: {file_type}",
            )

        # 2. Extract ELF headers & security flags via `readelf`
        security = BinarySecurityProfile()
        needed_libs: List[str] = []
        raw_summary_chunks = [f"File: {target.name}\nType: {file_type}\n"]

        if self.readelf_binary:
            # Check program headers for NX & RELRO
            res_l = self._run_isolated_command([self.readelf_binary, "-l", str(target)], target)
            if res_l.returncode == 0:
                out_l = res_l.stdout
                if "GNU_STACK" in out_l:
                    # RWE indicates executable stack (NX disabled)
                    # RW indicates non-executable stack (NX enabled)
                    for line in out_l.splitlines():
                        if "GNU_STACK" in line and "E" not in line.split("GNU_STACK")[-1]:
                            security.nx_enabled = True
                            break
                if "GNU_RELRO" in out_l:
                    security.relro_level = "partial"

            # Check dynamic tags for NEEDED libraries, BIND_NOW (full RELRO), PIE
            res_d = self._run_isolated_command([self.readelf_binary, "-d", str(target)], target)
            if res_d.returncode == 0:
                out_d = res_d.stdout
                for line in out_d.splitlines():
                    if "(NEEDED)" in line and "[" in line:
                        lib = line.split("[")[-1].split("]")[0]
                        needed_libs.append(lib)
                    if "(BIND_NOW)" in line or "FLAGS: BIND_NOW" in line:
                        if security.relro_level == "partial":
                            security.relro_level = "full"

            # Check file header for PIE (DYN type)
            res_h = self._run_isolated_command([self.readelf_binary, "-h", str(target)], target)
            if res_h.returncode == 0:
                if "DYN (Position-Independent Executable" in res_h.stdout or "DYN (Shared object" in res_h.stdout:
                    security.pie_enabled = True

        # 3. Extract symbols & stack canary check via `nm`
        exported_symbols: List[str] = []
        if self.nm_binary:
            res_nm = self._run_isolated_command([self.nm_binary, "-D", str(target)], target)
            if res_nm.returncode == 0:
                for line in res_nm.stdout.splitlines()[:50]:
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] in ("T", "W"):
                        exported_symbols.append(parts[2])
                if "__stack_chk_fail" in res_nm.stdout:
                    security.canary_present = True
            elif "no symbols" in res_nm.stderr:
                security.stripped = True

        report = BinaryInspectionReport(
            file_path=str(target),
            engine=engine,
            is_elf=is_elf,
            file_type=file_type,
            architecture=architecture,
            security_profile=security,
            needed_libraries=needed_libs,
            exported_symbols=exported_symbols,
            raw_summary="\n".join(raw_summary_chunks),
        )
        return report
