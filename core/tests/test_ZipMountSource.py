#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# pylint: disable=wrong-import-order
# pylint: disable=wrong-import-position
# pylint: disable=protected-access

import os
import sys
import shutil
import subprocess
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ratarmountcore import ZipMountSource  # noqa: E402

try:
    import pyminizip
except ImportError:
    pyminizip = None  # type: ignore


def findTestFile(relativePathOrName):
    for i in range(3):
        path = os.path.sep.join([".."] * i + ["tests", relativePathOrName])
        if os.path.exists(path):
            return path
    return relativePathOrName


password = "foo"


def create_encrypted_test_file(path):
    old_working_directory = os.getcwd()

    files = {
        "random-8MiB": os.urandom(8 * 1024 * 1024),
        "digits-8MiB": b'01234567' * (1024 * 1024),
    }

    folder = None
    try:
        folder = tempfile.TemporaryDirectory()
        os.chdir(folder.name)
        for name, contents in files.items():
            with open(name, "wb") as file:
                file.write(contents)

        if os.path.exists(path):
            os.remove(path)

        command = []
        if shutil.which("zip"):
            command = ["zip", "--encrypt", "--password", password, str(path)] + list(files.keys())
        elif shutil.which("7z") or shutil.which("7z.exe"):
            binary = "7z" if shutil.which("7z") else "7z.exe"
            command = [binary, "a", "-p" + password, str(path)] + list(files.keys())
        elif 'pyminizip' in sys.modules:
            print("Create zip file with pyminizip.")
            pyminizip.compress_multiple(list(files.keys()), [], str(path), password, 3)

        if command:
            print("Create zip file with:", " ".join(command))
            subprocess.run(command, check=True)
    finally:
        os.chdir(old_working_directory)
        if folder is not None:
            shutil.rmtree(folder.name)
    return files


class TestZipMountSource:
    @staticmethod
    def test_simple_usage():
        with ZipMountSource(findTestFile('folder-symlink.zip')) as mountSource:
            for folder in ['/', '/foo', '/foo/fighter']:
                assert mountSource.getFileInfo(folder)
                assert mountSource.fileVersions(folder) == 1
                assert mountSource.listDir(folder)

            for filePath in ['/foo/fighter/ufo']:
                assert mountSource.getFileInfo(filePath)
                assert mountSource.fileVersions(filePath) == 1
                assert not mountSource.listDir(filePath)
                with mountSource.open(mountSource.getFileInfo(filePath)) as file:
                    assert file.read() == b'iriya\n'

            # Links are not resolved by the mount source but by FUSE, i.e., descending into a link to a folder
            # will not work. This behavior may change in the future.
            for linkPath in ['/foo/jet']:
                assert mountSource.getFileInfo(linkPath)
                assert mountSource.fileVersions(linkPath) == 1
                assert not mountSource.listDir(linkPath)
                fileInfo = mountSource.getFileInfo(linkPath)
                assert fileInfo.linkname == 'fighter'
                with mountSource.open(mountSource.getFileInfo(linkPath)) as file:
                    # Contents of symlink is the symlink destination itself.
                    # This behavior is not consistent with other MountSources and therefore subject to change!
                    assert file.read() == b'fighter'


def benchmark_fast_zipfile_decryption():
    with tempfile.NamedTemporaryFile(suffix=".zip") as archive_path:
        files = create_encrypted_test_file(archive_path.name)
        with zipfile.ZipFile(archive_path.name) as archive:
            archive.setpassword(password.encode())
            assert set(archive.namelist()) == set(files.keys())

            t0 = time.time()
            for name, contents in files.items():
                with archive.open(name, "r") as file:
                    assert file.read() == contents
            t1 = time.time()
            duration = t1 - t0

            # On my local system: 6.2 s with Python, 0.1 s with this fix, with fix and pytest: 1.1 s !?
            # On Github Actions: 7.6 s with Python, 0.1 s with this fix
            # Thanks to the huge performance difference, this check should be sufficiently stable.
            print(f"Decryption took: {duration:.2e} s")
            assert duration < 1.0


def benchmark_fast_decryption():
    with tempfile.NamedTemporaryFile(suffix=".zip") as archive_path:
        files = create_encrypted_test_file(archive_path.name)
        with ZipMountSource(archive_path.name, passwords=[password.encode()]) as mountSource:
            t0 = time.time()
            for name, contents in files.items():
                with mountSource.open(mountSource.getFileInfo(name)) as file:
                    assert file.read() == contents
            t1 = time.time()
            duration = t1 - t0

            # On my local system: 6.2 s with Python, 0.1 s with this fix
            # On Github Actions: 7.6 s with Python, 0.1 s with this fix
            # Thanks to the huge performance difference, this check should be sufficiently stable.
            print(f"Decryption took: {duration:.2e} s")
            assert duration < 1.0


# We need to run these tests without pytest because, for some reason,
# pytest slows the zip decryption fix down from 0.1 s to 1.1 s?!
if __name__ == '__main__':
    benchmark_fast_zipfile_decryption()
    benchmark_fast_decryption()
