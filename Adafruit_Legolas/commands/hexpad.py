# Hex file pad command.
#
# Given a hex file, start address, end address, and optional pad byte it will
# generate a new hex file that includes all the data of the provided hex and
# fills in any empty spots with the provided pad byte. Good for extending a hex
# file and filling it with blank data to work around issues with programming tools.
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

from ..main import main, HexInt


@main.command(short_help='pad unused bytes inside a Intel format hex files')
@click.argument('input_file',
                nargs=1,
                metavar='INPUT_FILE',
                type=click.Path(exists=True))
@click.option('-o', '--output',
              type=click.Path(),
              help='output file (defaults to stdout)')
@click.option('-s', '--start',
              type=HexInt(),
              default=None,  # None value represents minimum address.
              metavar='ADDRESS (supports hex with 0x, like 0xFFFF)',
              help='start address.  Defaults to the first used address in the hex file (i.e. start).')
@click.option('-e', '--end',
              type=HexInt(),
              default=None,  # None value represents maximum address.
              metavar='ADDRESS (supports hex with 0x, like 0xFFFF)',
              help='end address.  Defaults to the last used address in the hex file (i.e. end).')
@click.option('-p', '--pad',
              type=HexInt(),
              default='0xFF',
              metavar='BYTE (supports hex with 0x, like 0xFF)',
              help='byte to use for padding.  Defaults to 0xFF.')
# Define the command code.  Notice how click will send in parsed parameters as
# arguments to the function.  Also note click will use the docstring as the
# full help text for the command.
def hexpad(input_file, output, start, end, pad):
    """Pad unused bytes of Intel format hex.

    Given a hex file this command will fill in any unused bytes with a padding
    byte.  By default the command will start from the first used address and pad
    all unused bytes up to the last used address (i.e. end of file) with the
    value 0xFF. You can specify an optional start address, end address, and
    padding byte value to override the default behavior.

    For example to pad all unused bytes in a hex with 0xFF run the command with
    the defaults:

      legolas hexpad input_file.hex

    By default the padded hex file is written to standard output, however use
    the output option to write to a file, like:

      legolas hexpad input_file.hex --output padded_file.hex

    To change the start address, end address, and padding byte use their options
    like:

      legolas hexpad input_file.hex --start 0x1000 --end 0xF000 --pad 0x00

    The above command will only pad unused bytes in the range 0x1000 - 0xF000
    (inclusive) with the value 0x00.
    """
    input_hex = intelhex.IntelHex(input_file)
    padded = intelhex.IntelHex()
    # Set start and end address to min and max address if not specified.
    if start is None:
        start = input_hex.minaddr()
    if end is None:
        end = input_hex.maxaddr()
    # Fail if either address is negative for some reason (bad input value).
    if start < 0 or end < 0:
        raise click.ClickException('Start and end address must be positive!')
    # Also fail if the end address is before the start address.
    if end < start:
        raise click.ClickException('End address must be after start address!')
    # Fill the padded file address range with the pad byte.
    for i in range(start, end+1):  # Use end+1 to make sure last address is padded.
        padded[i] = pad & 0xFF
    # Now merge in the input file on top of the pad bytes, this will make the
    # unused bytes have the pad byte.
    padded.merge(input_hex, overlap='replace')
    # Default to stdout if no output file is provided.
    if output is None:
        output = sys.stdout
    # Write out the padded file.
    padded.write_hex_file(output, True)  # Second param is bool to write start address.
