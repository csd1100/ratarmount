#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# pylint: disable=wrong-import-order
# pylint: disable=wrong-import-position
# pylint: disable=protected-access

import io
import os
import sys
import tarfile
import tempfile
import time

import pytest

from helpers import copyTestFile, findTestFile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ratarmountcore.SquashFSMountSource import SquashFSMountSource  # noqa: E402


class TestLibarchiveMountSource:
    @staticmethod
    @pytest.mark.parametrize('compression', ['no-compression', 'gzip', 'lz4', 'lzma', 'lzo', 'xz', 'zstd'])
    def test_simple_usage(compression):
        with copyTestFile(f'folder-symlink.{compression}.squashfs') as path, SquashFSMountSource(path) as mountSource:
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
