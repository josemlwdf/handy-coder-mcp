# `list_dir`

## Purpose

List files and subdirectories directly inside one workspace directory.

## Parameters

- `path` (required): workspace-relative directory path. Use `.` for the workspace root.

## Results

Returns `path`, `files`, `directories`, and `errors`. Entry paths are workspace-relative and sorted by name. The listing is one level deep; use `find_files` for recursive substring search.

## Safety

The directory and file symlinks are checked against the configured workspace root.
