#!/usr/bin/env pwsh

$ErrorActionPreference = 'Stop'

$status = git status --short
if ($status) {
    Write-Output $status
    throw 'Working tree is not clean.'
}

Write-Output 'Working tree is clean.'
