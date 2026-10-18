"""Typed destination conflicts shared by verified publication and its UI."""


class ExportFileConflict(FileExistsError):
    """A conclusive content/type conflict, not an inspection failure."""


class ExportFileContentConflict(ExportFileConflict):
    """Complete stable regular-file inspection found different frozen bytes."""
