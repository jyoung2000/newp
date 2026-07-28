"""Architectural test for the human-in-the-loop contract (CAPTCHA_POLICY.md).

JobPilot never solves, bypasses, predicts, outsources or automates a CAPTCHA
or human-verification challenge. This test fails the build if any known
solver service, stealth/evasion tooling, or challenge-directed OCR path
appears anywhere in the source tree or the dependency manifests.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.conftest import REPO_ROOT

# Case-insensitive substrings that must not appear anywhere in the tree.
# Solver services:
SOLVER_MARKERS = [
    "2captcha",
    "twocaptcha",
    "anti-captcha",
    "anticaptcha",
    "capmonster",
    "capsolver",
    "deathbycaptcha",
    "death-by-captcha",
    "azcaptcha",
    "rucaptcha",
    "imagetyperz",
    "bestcaptchasolver",
    "captchacoder",
    "endcaptcha",
    "nopecha",
    "captchaai",
    "solvecaptcha",
]
# Detection-evasion / cloaking tooling (§3: humanized input is not cloaking):
EVASION_MARKERS = [
    "undetected-chromedriver",
    "undetected_chromedriver",
    "playwright-stealth",
    "playwright_stealth",
    "puppeteer-extra-plugin-stealth",
    "selenium-stealth",
    "selenium_stealth",
    "fake-useragent",
    "fake_useragent",
]
# OCR / audio-transcription libraries that would only exist here to aim at a
# challenge. (JobPilot has no other image/audio-recognition feature.)
OCR_AUDIO_MARKERS = [
    "pytesseract",
    "easyocr",
    "speechrecognition",
    "speech_recognition",
    "openai-whisper",
    "whisperx",
]

ALL_MARKERS = SOLVER_MARKERS + EVASION_MARKERS + OCR_AUDIO_MARKERS

# Files allowed to mention the markers: this test and the policy documents
# that state the ban.
ALLOWED_FILES = {
    "backend/tests/test_captcha_policy.py",
    "CAPTCHA_POLICY.md",
    "docs/SOURCES.md",
}

TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".toml", ".cfg", ".ini",
    ".yml", ".yaml", ".md", ".txt", ".html", ".css", ".sh", ".lock",
    ".example", ".conf", ".mk", "", ".xml", ".svg",
}


def _tracked_and_untracked_files() -> list[Path]:
    """Everything under version control plus new files not yet committed."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line.strip()]


def test_no_captcha_solver_or_evasion_tooling_anywhere() -> None:
    pattern = re.compile("|".join(re.escape(m) for m in ALL_MARKERS), re.IGNORECASE)
    violations: list[str] = []
    for path in _tracked_and_untracked_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED_FILES or not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            violations.append(f"{rel}:{line_no}: {match.group(0)!r}")
    assert not violations, (
        "CAPTCHA-solver / evasion tooling reference found. "
        "JobPilot's human-in-the-loop contract (CAPTCHA_POLICY.md) forbids these:\n"
        + "\n".join(violations)
    )


def test_dependency_manifests_are_clean() -> None:
    """Dependency trees must not pull in solver SDKs even transitively —
    check every manifest and lockfile by name."""
    manifests = []
    for pat in ("pyproject.toml", "uv.lock", "package.json", "package-lock.json"):
        manifests.extend(REPO_ROOT.rglob(pat))
    pattern = re.compile("|".join(re.escape(m) for m in ALL_MARKERS), re.IGNORECASE)
    violations = []
    for path in manifests:
        if "node_modules" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        for match in pattern.finditer(text):
            violations.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)!r}")
    assert not violations, "Solver/evasion dependency found:\n" + "\n".join(violations)


def test_policy_document_exists() -> None:
    policy = REPO_ROOT / "CAPTCHA_POLICY.md"
    assert policy.is_file(), "CAPTCHA_POLICY.md must exist at the repository root"
    text = policy.read_text()
    for required in ("never", "human"):
        assert required in text.lower()
