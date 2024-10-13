#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# pylint: disable=abstract-method,unused-argument

import stat

import fsspec

from .MountSource import MountSource
from .SQLiteIndexedTar import SQLiteIndexedTar
from .utils import overrides


class MountSourceFileSystem(fsspec.spec.AbstractFileSystem):
    """A thin adaptor from the MountSource interface to the fsspec AbstractFileSystem interface."""

    cachable = False

    def __init__(self, mountSource: MountSource, **kwargs):
        super().__init__(**kwargs)
        self.mountSource = mountSource

    @classmethod
    def _stripProtocol(cls, path):
        return path[-len(cls.protocol) - 3] if path.startswith(cls.protocol + '://') else path

    @staticmethod
    def _fileInfoToDict(name, fileInfo):
        return {
            "type": "directory" if stat.S_ISDIR(fileInfo.mode) else "file",
            "name": name,
            "mode": f"{fileInfo.mode:o}",
            "size": fileInfo.size,
        }

    @overrides(fsspec.spec.AbstractFileSystem)
    def ls(self, path, detail=True, **kwargs):
        strippedPath = self._stripProtocol(path)
        if detail:
            result = self.mountSource.listDir(strippedPath)
            if result is None:
                raise FileNotFoundError(path)
            if not isinstance(result, dict):
                result = {name: self.mountSource.getFileInfo(name) for name in result}
            return [self._fileInfoToDict(name, info) for name, info in result.items() if info is not None]

        result = self.mountSource.listDirModeOnly(strippedPath)
        if result is None:
            raise FileNotFoundError(path)
        return list(result.keys()) if isinstance(result, dict) else result

    @overrides(fsspec.spec.AbstractFileSystem)
    def info(self, path, **kwargs):
        result = self.mountSource.getFileInfo(self._stripProtocol(path))
        if result is None:
            raise FileNotFoundError(path)
        return self._fileInfoToDict(path, result)

    @overrides(fsspec.spec.AbstractFileSystem)
    def _open(
        self,
        path,
        mode="rb",
        block_size=None,
        autocommit=True,
        cache_options=None,
        **kwargs,
    ):
        if mode != "rb":
            raise ValueError("Only binary reading is supported!")
        fileInfo = self.mountSource.getFileInfo(self._stripProtocol(path))
        if fileInfo is None:
            raise FileNotFoundError(path)
        return self.mountSource.open(fileInfo, buffering=block_size if block_size else -1)


class SQLiteIndexedTarFileSystem(MountSourceFileSystem):
    """
    Browse the files of a (compressed) TAR archive quickly.

    This is a more optimized alternative to fsspec.implementations.TarFileSystem.
    """

    protocol = "ratar"

    def __init__(
        self,
        # It must be called "fo" for URL chaining to work!
        # https://filesystem-spec.readthedocs.io/en/latest/features.html#url-chaining
        fo=None,
        *,  # force all parameters after to be keyword-only
        target_options=None,
        target_protocol=None,
        **kwargs,
    ):
        """Refer to SQLiteIndexedTar for all supported arguments and options."""

        options = kwargs.copy()

        self._openFile = None
        if isinstance(fo, str):
            # Implement URL chaining such as when calling fsspec.open("ratar://bar::file://single-file.tar").
            if target_protocol:
                self._openFile = fsspec.open(fo, protocol=target_protocol, **target_options)
                # Set the TAR file name so that the index can be found/stored accordingly.
                if target_protocol == 'file':
                    options['tarFileName'] = fo
                    if 'indexFilePath' not in options:
                        options['indexFilePath'] = fo + ".index.sqlite"
                    if 'writeIndex' not in options:
                        options['writeIndex'] = True
                if isinstance(self._openFile, fsspec.core.OpenFiles):
                    self._openFile = self._openFile[0]
                fo = self._openFile.open()
            else:
                options['tarFileName'] = fo
                if 'writeIndex' not in options:
                    options['writeIndex'] = True
                fo = None

        if fo:
            options['fileObject'] = fo

        super().__init__(SQLiteIndexedTar(**options))


# Only in case the entry point hooks in the pyproject.toml are not working for some reason.
fsspec.register_implementation("ratar", SQLiteIndexedTarFileSystem, clobber=True)
