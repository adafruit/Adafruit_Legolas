# Legolas main entry point.
#
# This is the main entry point for the program using the click command line
# contruction toolkit.  The main group defined here can be used as a decorator
# to create new subcommands (see commands subfolder for subcommand implementations).
#
# Author: Tony DiCola
from . import __version__

import click


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
