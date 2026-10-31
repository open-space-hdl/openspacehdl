"""Errors of openspacehdl."""


class OshError(Exception):
    """An error of openspacehdl; the message says what to do."""


class LockError(OshError):
    """The lock manifest is missing, damaged, or its inputs break a consistency rule."""
