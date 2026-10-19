"""Build, package and release Houdini-NetworkTethers.

    python build.py build [--hfs PATH]   build/Houdini-NetworkTethers: the package
                                         with its toolbar generated for one local
                                         Houdini, ready to point a package at
    python build.py dist                 dist/Houdini-NetworkTethers-<version>.zip:
                                         the package without SideFX content
    python build.py release [--draft]    dist, then tag v<version> and create the
                                         GitHub release (notes from CHANGELOG.md)

Nothing derived from SideFX files goes into git, dist or a release: installed
packages generate their toolbar from the local Houdini at startup.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
NAME = "Houdini-NetworkTethers"
EXCLUDE_DIRS = {"generated", "__pycache__"}
EXTRA_FILES = ("README.md", "CHANGELOG.md", "LICENSE")

sys.path.insert(0, os.path.join(SRC, "python3.11libs"))
from tethers import __version__ as VERSION  # noqa: E402
from tethers import toolbar  # noqa: E402


def find_hfs():
    if os.environ.get("HFS"):
        return os.environ["HFS"]
    candidates = glob.glob(r"C:\Program Files\Side Effects Software\Houdini 21.0.*")
    if not candidates:
        sys.exit("No Houdini 21.0 found: pass --hfs or set HFS.")
    return max(candidates, key=lambda p: [int(n) for n in re.findall(r"\d+", os.path.basename(p))])


def build_of(hfs):
    match = re.search(r"(\d+\.\d+\.\d+)", os.path.basename(os.path.normpath(hfs)))
    if not match:
        sys.exit("Can't read the Houdini build from %s." % hfs)
    return match.group(1)


def package_files():
    """(source path, path inside the package) for every distributable file."""
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            path = os.path.join(dirpath, name)
            yield path, os.path.relpath(path, SRC)
    for name in EXTRA_FILES:
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            yield path, name


def cmd_build(args):
    hfs = args.hfs or find_hfs()
    build = build_of(hfs)
    out = os.path.join(ROOT, "build", NAME)
    shutil.rmtree(out, ignore_errors=True)
    for path, rel in package_files():
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
    toolbar.generate(hfs, toolbar.generated_dir(build, out), build)
    print("Built %s %s for Houdini %s: %s" % (NAME, VERSION, build, out))


def cmd_dist(args):
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    archive = os.path.join(ROOT, "dist", "%s-%s.zip" % (NAME, VERSION))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, rel in package_files():
            zf.write(path, os.path.join(NAME, rel))
    print("Packaged %s" % archive)
    return archive


def release_notes():
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"^## %s\b.*?\n(.*?)(?=^## |\Z)" % re.escape(VERSION), text, re.M | re.S)
    if not match:
        sys.exit("No '## %s' section in CHANGELOG.md." % VERSION)
    return match.group(1).strip()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def cmd_release(args):
    tag = "v" + VERSION
    if git("status", "--porcelain"):
        sys.exit("Commit or stash your changes first.")
    if git("tag", "--list", tag):
        sys.exit("Tag %s already exists: bump __version__ first." % tag)
    notes = release_notes()
    archive = cmd_dist(args)
    git("tag", "-a", tag, "-m", tag)
    git("push", "origin", tag)
    command = ["gh", "release", "create", tag, archive, "--title", tag, "--notes", notes]
    if args.draft:
        command.append("--draft")
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="package with toolbar generated for a local Houdini")
    p.add_argument("--hfs", help="Houdini install folder (default: $HFS or newest 21.0)")
    p.set_defaults(func=cmd_build)
    sub.add_parser("dist", help="distributable zip").set_defaults(func=cmd_dist)
    p = sub.add_parser("release", help="dist + tag + GitHub release")
    p.add_argument("--draft", action="store_true", help="create the release as a draft")
    p.set_defaults(func=cmd_release)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
