# ELF file SQL-style query command.
#
# Query the attributes of an ELF file using a SQL query syntax.
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
import cmd
import sqlite3
import sys

import click
from elftools.common.py3compat import bytes2str
from elftools.elf.elffile import ELFFile
from elftools.elf.descriptions import *
from elftools.elf.sections import SymbolTableSection
from tabulate import tabulate

from ..main import main


# Symbol table column names and types.
SYMBOL_COLS = [('Number',       'integer primary key autoincrement'),
               ('Value',        'integer'),
               ('Size',         'integer'),
               ('Type',         'text'),
               ('Binding',      'text'),
               ('Visibility',   'text'),
               ('SectionIndex', 'text'),
               ('Name',         'text'),
               ('Section',      'text')]

# Section header table column names and types.
SECTION_COLS = [('Number',    'integer primary key'),
                ('Name',      'text'),
                ('Type',      'text'),
                ('Flags',     'text'),
                ('Address',   'integer'),
                ('Offset',    'integer'),
                ('Size',      'integer'),
                ('Link',      'integer'),
                ('Info',      'integer'),
                ('Alignment', 'integer'),
                ('EntrySize', 'integer')]

# Example queries that are shown in documentation:
EXAMPLES = """The following are example queries:

To list every symbol in order:

  SELECT * FROM symbols ORDER BY Number ASC

Note that a TO_HEX function is available which can convert a column to a 
zero-padded hexadecimal string of the specified width for easier reading.
For example to grab the name and value of each symbol:

  SELECT Name, TO_HEX(Value, 8) FROM symbols ORDER BY Number ASC

To select the name of each symbol related to the '.bss' section:

  SELECT Name FROM symbols WHERE Section = '.bss'"

To do the same query but also restrict it to symbols with size > 256 bytes:

  SELECT Name FROM symbols WHERE Section = '.bss' AND Size > 256"

There is also a FROM_HEX function that can be used to filter against hex values
easily.  For example to select all symbols with value between 0xFF and 0xFFFF:

  SELECT Name, TO_HEX(Value, 8) FROM symbols WHERE Value > FROM_HEX('FF') AND Value < FROM_HEX('FFFF')

To select all symbol data for symbols that are of type 'FUNC' or 'OBJECT':

  SELECT * FROM symbols WHERE Type IN ('FUNC', 'OBJECT')

To select the name and size of the 5 largest symbols:

  SELECT Name, Size FROM symbols ORDER BY Size DESC LIMIT 5

To list all variables in RAM ('.bss' section) sorted by size:

  SELECT to_hex(Value, 8), Size, Section, Name FROM symbols WHERE Section = ".bss" AND Size > 0 ORDER BY Size Asc

You can even do more advanced queries like counting how many unique Type
values exist:

  SELECT Type, COUNT(*) AS Count FROM symbols GROUP BY Type ORDER BY Count DESC

Any query supported by SQLite is possible!
"""

# Main help for the program (builds on the examples above).
USAGE = """Query ELF symbols using a SQL-style query.

Provide two arguments, a path to an ELF file and an optional SQL query to 
make against the file.  The SQL query should be made against the table 
'symbols' and it contains a row for each symbol.  In addition there is a 
'sections' table that lists information about each section.  See the
--list-columns option to list all the columns and tables.

If no query is provided then an interactive command loop will start where 
multiple queries can be run successively.

Results will be written as a friendly table format to standard output by
default.  However look at the --output option to write results to a file,
and the --output-format option to write results in a machine-friendly format
like a comma or tab separated file.  Note that the output and output format
options are ignored in interactive query mode.
"""


class ELFQuery(object):
    # Class to support query of ELF file using SQL. Adapted from readelf.py 
    # example at:
    #   https://github.com/eliben/pyelftools/blob/master/scripts/readelf.py

    def __init__(self, input_file):
        # Parse ELF file and populate DB table with data.
        self.elffile = ELFFile(input_file)
        self._init_db()
        self._load_db()

    def _init_db(self):
        """Setup the in-memory database for symbol and section data."""
        # Initialize in memory SQLite DB to hold ELF data.
        self.db = sqlite3.connect(':memory:')
        # Add custom functions for hex conversion (although the latest SQLite
        # versions support hex conversions natively, Mac OSX has a very old
        # version of SQLite with Python and needs these functions).
        self.db.create_function('to_hex', 2, to_hex)
        self.db.create_function('from_hex', 1, from_hex)
        # Create sections table.
        # Create column specification of form like "<name> <type>, <name> <type>, etc."
        column_spec = ', '.join(map(lambda x: '{0} {1}'.format(x[0], x[1]), SECTION_COLS))
        self.db.execute('CREATE TABLE sections ({0})'.format(column_spec))
        # Create symbols table.
        column_spec = ', '.join(map(lambda x: '{0} {1}'.format(x[0], x[1]), SYMBOL_COLS))
        self.db.execute("CREATE TABLE symbols ({0})".format(column_spec))
        self.db.commit()

    def _load_db(self):
        """Load symbol and section data into the database."""
        # Load ELF section metadata.
        for nsec, section in enumerate(self.elffile.iter_sections()):
            self.db.execute('INSERT INTO sections VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                            (nsec,
                             bytes2str(section.name).strip(),
                             describe_sh_type(section['sh_type']).strip(),
                             describe_sh_flags(section['sh_flags']).strip(),
                             section['sh_addr'],
                             section['sh_offset'],
                             section['sh_size'],
                             section['sh_link'],
                             section['sh_info'],
                             section['sh_addralign'],
                             section['sh_entsize']))
            self.db.commit()

        # Load ELF symbol data into DB.  Adapted from readelf.py.
        for section in self.elffile.iter_sections():
            if not isinstance(section, SymbolTableSection):
                continue
            if section['sh_entsize'] == 0:
                continue
            for nsym, symbol in enumerate(section.iter_symbols()):
                # Get the related section header index and name for this symbol.
                shndx = describe_symbol_shndx(symbol['st_shndx']).strip()
                related_section = None
                if str.isdigit(shndx):
                    sec = self._get_section(shndx)
                    if sec is not None:
                        related_section = sec[1]
                # Write the symbol value to the table.
                self.db.execute('INSERT INTO symbols VALUES (NULL,?,?,?,?,?,?,?,?)',
                                (symbol['st_value'],
                                 symbol['st_size'],
                                 describe_symbol_type(symbol['st_info']['type']).strip(),
                                 describe_symbol_bind(symbol['st_info']['bind']).strip(),
                                 describe_symbol_visibility(symbol['st_other']['visibility']).strip(),
                                 shndx,
                                 bytes2str(symbol.name).strip(),
                                 related_section))
                self.db.commit()

    def _get_section(self, index):
        """Retrieve the specified section row at the provided index."""
        return self.db.execute('SELECT * FROM sections WHERE Number = ?', (index,)).fetchone()

    def query(self, query):
        """Perform SQL query against symbols and return result rows and column
        names.
        """
        cursor = self.db.execute(query)
        columns = map(lambda x: x[0], cursor.description)
        return (cursor.fetchall(), columns)


class InteractiveELFQuery(cmd.Cmd):
    """Python Cmd module implementation for a simple interactive query loop."""
    # Change the prompt for the command loop.
    prompt = 'SQL> '

    def __init__(self, elfquery):
        # cmd.Cmd is an old style class and can't use super, so call the init
        # directly.
        cmd.Cmd.__init__(self)
        self.elfquery = elfquery

    def do_quit(self, line):
        """Quit the program."""
        sys.exit(0)

    def do_exit(self, line):
        """Quit the program."""
        sys.exit(0)

    def do_columns(self, line):
        """List the columns available to query."""
        print_columns()

    def do_examples(self, line):
        """Display example queries."""
        click.echo(EXAMPLES)

    def default(self, query):
        """Run query against ELF file."""
        try:
            result, columns = self.elfquery.query(query)
            print_results(result, columns, sys.stdout, 'friendly')
        except sqlite3.Error as ex:
            click.echo('ERROR: {0}'.format(ex.message))


def to_hex(number, width):
    """Convert number to hex value with specified width.  Will be padded by zero
    to fill the width.
    """
    format_string = '{{0:0{0}X}}'.format(width)
    return format_string.format(number)


def from_hex(value):
    """Convert hex string to an integer value."""
    return int(value, 16)


def print_columns():
    """Print out the list of columns."""
    click.echo("Table 'sections' has the following columns:")
    for col in SECTION_COLS:
        click.echo('- {0}'.format(col[0]))
    click.echo('Key to Flags column values:')
    click.echo('W (write), A (alloc), X (execute), M (merge), S (strings), l (large)')
    click.echo('I (info), L (link order), G (group), T (TLS), E (exclude), x (unknown)')
    click.echo('O (extra OS processing required), o (OS specific), p (processor specific)')
    click.echo('')
    click.echo("Table 'symbols' has the following columns:")
    for col in SYMBOL_COLS:
        click.echo('- {0}'.format(col[0]))


def list_columns(ctx, param, value):
    """Called when the --list-columns option is parsed.  Print out columns and 
    stop any further processing.
    """
    if not value or ctx.resilient_parsing:
        return
    print_columns()
    ctx.exit()


def print_results(result, columns, output, output_format):
    """Print out the results of a query to the specified output and using the
    specified output format.
    """
    if output_format == 'friendly':
        output.write(tabulate(result, columns))
        output.write('\n\n')
        output.write('Query returned {0} rows.\n\n'.format(len(result)))
    elif output_format == 'csv':
        for row in result:
            output.write(','.join(map(lambda x: str(x).strip(), row)))
            output.write('\n')
    elif output_format == 'tsv':
        for row in result:
            output.write('\t'.join(map(lambda x: str(x).strip(), row)))
            output.write('\n')
    else:
        raise click.UsageError('Unknown output format!')


@main.command(help='{0}\n\n{1}'.format(USAGE, EXAMPLES))
# Take an ELF file path to query as input.
@click.argument('input_file',
                metavar='FILE',
                type=click.File('rb'))
# Also take a string to use as the query.  This is optional and if not provided
# the program will enter an interactive query mode.
@click.argument('query',
                required=False,
                metavar='"QUERY"')
# Add option to list all the attributes/columns that can be queried.
# This is an eager callback that will quit the program immediately, see:
#   http://click.pocoo.org/4/options/#callbacks-and-eager-options
@click.option('--list-columns',
              is_flag=True,
              callback=list_columns,
              expose_value=False,
              is_eager=True,
              help='list symbol attributes/columns that can be queried')
# Add option to change how data is displayed, either in a friendly human-readable
# format, or as a machine-friendly parseable format like CSV, TSV, etc.
@click.option('--output-format', '-f',
              type=click.Choice(['friendly','csv','tsv']),
              default='friendly',
              help='format for results (default is friendly human-readable table)')
# Add option to output to a file (default is standard output).
@click.option('--output', '-o',
              type=click.File('wb'),
              default=sys.stdout,
              help='result file (default is standard output)')
# Define the command code.  Notice how click will send in parsed parameters as
# arguments to the function.
def elfquery(input_file, query, output_format, output):
    elfquery = ELFQuery(input_file)
    if query is not None:
        # Query was sent in command line, process it and then exit.
        result, columns = elfquery.query(query)
        print_results(result, columns, output, output_format)
    else:
        # Interactive mode using a command loop.
        click.echo('Interactive query mode.  Enter query at prompt, help for command list, or quit to exit program.')
        loop = InteractiveELFQuery(elfquery)
        loop.cmdloop()
