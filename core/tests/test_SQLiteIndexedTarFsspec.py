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

import fsspec

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ratarmountcore.SQLiteIndexedTarFsspec import SQLiteIndexedTarFileSystem as ratarfs  # noqa: E402


def findTestFile(relativePathOrName):
    for i in range(3):
        path = os.path.sep.join([".."] * i + ["tests", relativePathOrName])
        if os.path.exists(path):
            return path
    return relativePathOrName


def test_fileSystem():
    fs = ratarfs(findTestFile('single-file.tar'))

    assert 'bar' in fs.ls("/", detail=False)
    assert 'bar' in [info['name'] for info in fs.ls("/", detail=True)]

    assert not fs.isfile("/")
    assert fs.isdir("/")
    assert fs.exists("/")

    assert fs.isfile("/bar")
    assert not fs.isdir("/bar")
    assert not fs.exists("/bar2")

    assert fs.cat("/bar") == b"foo\n"
    assert fs.cat("bar") == b"foo\n"

    with fs.open("bar") as file:
        assert file.read() == b"foo\n"


def test_URLContextManager():
    with fsspec.open("ratar://bar::file://" + findTestFile('single-file.tar')) as file:
        assert file.read() == b"foo\n"


def test_URL():
    openedFile = fsspec.open("ratar://bar::file://" + findTestFile('single-file.tar'))
    with openedFile as file:
        assert file.read() == b"foo\n"


def test_pandas():
    if pd is None:
        return

    with tempfile.TemporaryDirectory(suffix=".test.ratarmount") as folderPath:
        oldPath = os.getcwd()
        os.chdir(folderPath)
        try:
            with open("test.csv", "wb") as file:
                file.write(b"1,2\n3,4")
            with tarfile.open("test-csv.tar", "w") as archive:
                archive.add("test.csv")

            # Pandas seems
            data = pd.read_csv("ratar://test.csv::file://test-csv.tar", compression=None, header=None)
            assert data.iloc[0, 1] == 2
        finally:
            os.chdir(oldPath)

if False:
    # I had problems with resource deallocation!
    # For Rapidgzip it becomes important because of the background threads.
    # I can only reproduce this bug when run in global namespace.
    # It always works without problems inside a function.
    # TODO I don't know how to fix this. Closing the file object in SQLiteIndexedTar.__del__
    #      would fix this particular error, but  itwould lead to other errors for recursive mounting
    #      and when using fsspec.open chained URLs...
    #      Only calling join_threads also does not work for some reason.
    #      Checking with sys.getrefcount and only closing it if it is the only one left also does not work
    #      because the refcount is 3 inside __del__ for some reason.
    #      Closing the file inside RapidgzipFile.__del__ also does not work because it results in the
    #      same error during that close call, i.e., it is already too late at that point. I'm not sure
    #      why it is too late there but not too late during the SQLiteIndexedTar destructor...
    #      Maybe there are also some cyclic dependencies?
    with tempfile.TemporaryDirectory(suffix=".test.ratarmount") as folderPath:
        contents = os.urandom(96 * 1024 * 1024)

        tarPath = os.path.join(folderPath, "random-data.tar.gz")
        with tarfile.open(name=tarPath, mode="w:gz") as tarArchive:
            # Must create a sufficiently large .tar.gz so that rapidgzip is actually used.
            # In the future this "has multiple chunks" rapidgzip test is to be removed and
            # this whole test becomes redundant.
            tinfo = tarfile.TarInfo("random-data")
            tinfo.size = len(contents)
            tarArchive.addfile(tinfo, io.BytesIO(contents))

        # Only global variables trigger the "Detected Python finalization from running rapidgzip thread." bug.
        # I am not sure why. Probably, because it gets garbage-collected later.
        globalOpenFile = fsspec.open("ratar://random-data::file://" + tarPath)
        with globalOpenFile as file:
            assert file.read() == contents

        # This is still some step the user has to do, but it cannot be avoided.
        # It might be helpful if fsspec had some kind of better resource management for filesystems though.
        del globalOpenFile
