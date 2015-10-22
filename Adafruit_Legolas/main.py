# Legolas main entry point.
#
# This is the main entry point for the program using the click command line
# contruction toolkit.  The main group defined here can be used as a decorator
# to create new subcommands (see commands subfolder for subcommand implementations).
#
# Author: Tony DiCola
#
# The MIT License (MIT)
#
# Copyright (c) 2015 Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from . import __version__

import click


# Useful click option type for a value that can be specified as hex or decimal.
class HexInt(click.ParamType):
    """Custom click parameter type for an integer which can be specified as a
    hex value (starts with 0x...), octal (starts with 0), or decimal value.
    """
    name = 'integer (supports hex with 0x)'

    def convert(self, value, param, ctx):
        # Allow null/none value.
        if value is None:
            return None
        # Use int class to automatically convert decimal, hex, etc. string to
        # a integer value.
        try:
            return int(value, 0)
        except:
            self.fail('%s is not a valid integer' % value, param, ctx)

    def __repr__(self):
        return 'INT'


@click.group()
@click.version_option(version=__version__)
def main():
    """Adafruit legolas is a tool to work with ELF and other binary & executable
    files for embedded systems.
    """
    # Nothing needs to be done in the main entry point.  Subcommands will take
    # over further processing.
    pass


# MUST have the star import below to make sure all commands are loaded.  Also
# move this to the end of the file to prevent circular references.
from .commands import *
