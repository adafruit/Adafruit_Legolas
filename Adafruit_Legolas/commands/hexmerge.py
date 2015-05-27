# Hex file merge command.
#
# Combine an arbitrary number of Intel .hex files into a single combined file.
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
import sys

import click
import intelhex

from ..main import main


# Definition of the hexmerge command follows below.  First the command is
# defined using the @main.command decorator.  The short_help is displayed in the
# help text that lists commands.
@main.command(short_help='merge Intel format hex files')
# Next all the parameters to the command are defined using click decorators
# below.  You can find more details on arguments, options, etc. at:
#   - http://click.pocoo.org/4/arguments/
#   - http://click.pocoo.org/4/options/
#   - http://click.pocoo.org/4/parameters/
# Take an unlimited number of input file paths (ensuring all exist first).
@click.argument('inputs', 
                nargs=-1,
                metavar='[FILE]...',
                type=click.Path(exists=True))
# Add option to specify the output file (default to none which will use stdout).
@click.option('-o', '--output', 
              type=click.Path(),
              help='output file (defaults to stdout)')
# Add option to pick how overlapping ranges are handled, either to fail with an
# error or to ignore them (last written wins).
@click.option('--overlap', 
              type=click.Choice(['error', 'ignore']),
              default='error',
              help='how to handle when hex files overlap.  Can be either error to fail (the default), or ignore to allow the overlap.')
# Define the command code.  Notice how click will send in parsed parameters as
# arguments to the function.  Also note click will use the docstring as the
# full help text for the command.
def hexmerge(inputs, output, overlap):
    """Merge Intel format hex files into a single file.

    Provide the path to each input file as a separate argument.  For example to
    merge three files run:
    
      adahex hexmerge file1.hex file2.hex file3.hex

    By default the merged hex file is written to standard output, however see
    the output option below to write to a file.
    """
    # Process all the input hex files and merge them into a single file.
    merged = intelhex.IntelHex()
    try:
        for filename in inputs:
            merged.merge(intelhex.IntelHex(filename), overlap)
    except intelhex.AddressOverlapError:
        raise click.ClickException('Detected overlap in address space of merged hex files!')
    # Default to stdout if no output file is provided.
    if output is None:
        output = sys.stdout
    # Write out the merged file.
    merged.write_hex_file(output, True)  # Second param is bool to write start address.
