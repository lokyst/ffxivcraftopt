"""Utilities."""

__author__ = 'Gordon Tyler <gordon@doxxx.net>'


class StringLogOutput(object):
    def __init__(self):
        self.logText = ""

    def write(self, s):
        self.logText = self.logText + s
