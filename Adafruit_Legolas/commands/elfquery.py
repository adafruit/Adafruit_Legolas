# ELF file SQL-style query command.
#
# Query the attributes of an ELF file using a SQL query syntax.
#
# Author: Tony DiCola
import cmd
import sqlite3
import sys

import click
from elftools.common.py3compat import bytes2str
from elftools.elf.dynamic import DynamicSection
from elftools.elf.elffile import ELFFile
from elftools.elf.descriptions import *
from elftools.elf.sections import SymbolTableSection
from elftools.elf.gnuversions import *
from tabulate import tabulate

from ..main import main


# Define symbol column names and types.
COLUMNS = [('Section', 'text not null'),
           ('Number',  'integer not null'),
           ('Value',   'text'),
           ('Size',    'integer'),
           ('Type',    'text'),
           ('Bind',    'text'),
           ('Vis',     'text'),
           ('Ndx',     'text'),
           ('Name',    'text')]


class ELFQuery(object):
    # Class to support query of ELF file using SQL. Adapted from readelf.py 
    # example at:
    #   https://github.com/eliben/pyelftools/blob/master/scripts/readelf.py

    def __init__(self, input_file):
        # Parse ELF file and populate DB table with data.
        self.elffile = ELFFile(input_file)
        self._init_versioninfo()
        # Initialize and load DB with parsed data.
        self._init_db()
        self._load_db()

    def _init_versioninfo(self):
        # Initialize version info from ELF sections.  Adapted from readelf.py.
        self._versioninfo = {'versym': None, 'verdef': None, 'verneed': None, 
                             'type': None}

        for section in self.elffile.iter_sections():
            if isinstance(section, GNUVerSymSection):
                self._versioninfo['versym'] = section
            elif isinstance(section, GNUVerDefSection):
                self._versioninfo['verdef'] = section
            elif isinstance(section, GNUVerNeedSection):
                self._versioninfo['verneed'] = section
            elif isinstance(section, DynamicSection):
                for tag in section.iter_tags():
                    if tag['d_tag'] == 'DT_VERSYM':
                        self._versioninfo['type'] = 'GNU'
                        break

        if not self._versioninfo['type'] and (self._versioninfo['verneed'] or \
                                              self._versioninfo['verdef']):
            self._versioninfo['type'] = 'Solaris'

    def _symbol_version(self, nsym):
        # Adapted from readelf.py.
        symbol_version = dict.fromkeys(('index', 'name', 'filename', 'hidden'))

        if not self._versioninfo['versym'] or nsym >= self._versioninfo['versym'].num_symbols():
            return None

        symbol = self._versioninfo['versym'].get_symbol(nsym)
        index = symbol.entry['ndx']
        if not index in ('VER_NDX_LOCAL', 'VER_NDX_GLOBAL'):
            index = int(index)

            if self._versioninfo['type'] == 'GNU':
                # In GNU versioning mode, the highest bit is used to
                # store wether the symbol is hidden or not
                if index & 0x8000:
                    index &= ~0x8000
                    symbol_version['hidden'] = True

            if self._versioninfo['verdef'] and index <= self._versioninfo['verdef'].num_versions():
                _, verdaux_iter = self._versioninfo['verdef'].get_version(index)
                symbol_version['name'] = bytes2str(next(verdaux_iter).name)
            else:
                verneed, vernaux = self._versioninfo['verneed'].get_version(index)
                symbol_version['name'] = bytes2str(vernaux.name)
                symbol_version['filename'] = bytes2str(verneed.name)

        symbol_version['index'] = index
        return symbol_version

    def _format_hex(self, addr, fieldsize=None, fullhex=False, lead0x=True,
                    alternate=False):
        # Adapted from readelf.py.
        if alternate:
            if addr == 0:
                lead0x = False
            else:
                lead0x = True
                fieldsize -= 2

        s = '0x' if lead0x else ''
        if fullhex:
            fieldsize = 8 if self.elffile.elfclass == 32 else 16
        if fieldsize is None:
            field = '%x'
        else:
            field = '%' + '0%sx' % fieldsize
        return s + field % addr

    def _init_db(self):
        # Initialize in memory SQLite DB to hold symbol data.
        self.db = sqlite3.connect(':memory:')
        # Create column specification of form like "<name> <type>, <name> <type>, etc."
        column_spec = ', '.join(map(lambda x: '{0} {1}'.format(x[0], x[1]), COLUMNS))
        self.db.execute("CREATE TABLE symbols ({0}, PRIMARY KEY (Section, Number))".format(column_spec))
        self.db.commit()

    def _load_db(self):
        # Load ELF symbol data into DB.  Adapted from readelf.py.
        for section in self.elffile.iter_sections():
            if not isinstance(section, SymbolTableSection):
                continue
            if section['sh_entsize'] == 0:
                continue
            for nsym, symbol in enumerate(section.iter_symbols()):
                version_info = ''
                if (section['sh_type'] == 'SHT_DYNSYM' and self._versioninfo['type'] == 'GNU'):
                    version = self._symbol_version(nsym)
                    if (version['name'] != bytes2str(symbol.name) and
                        version['index'] not in ('VER_NDX_LOCAL', 'VER_NDX_GLOBAL')):
                        if version['filename']:
                            # external symbol
                            version_info = '@%(name)s (%(index)i)' % version
                        else:
                            # internal symbol
                            if version['hidden']:
                                version_info = '@%(name)s' % version
                            else:
                                version_info = '@@%(name)s' % version
                # Add row to symbols table.
                self.db.execute('INSERT INTO symbols VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                (bytes2str(section.name), 
                                 nsym,
                                 self._format_hex(symbol['st_value'], fullhex=True, lead0x=False),
                                 symbol['st_size'],
                                 describe_symbol_type(symbol['st_info']['type']),
                                 describe_symbol_bind(symbol['st_info']['bind']),
                                 describe_symbol_visibility(symbol['st_other']['visibility']),
                                 describe_symbol_shndx(symbol['st_shndx']),
                                 bytes2str(symbol.name)))
                self.db.commit()

    def query(self, query):
        """Perform SQL query against symbols and return result rows and column
        names.
        """
        cursor = self.db.execute(query)
        columns = map(lambda x: x[0], cursor.description)
        return (cursor.fetchall(), columns)


class InteractiveELFQuery(cmd.Cmd):
    # Python Cmd module implementation for a simple interactive query loop.

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

    def default(self, query):
        """Run query against ELF file."""
        try:
            result, columns = self.elfquery.query(query)
            print_results(result, columns, sys.stdout, 'friendly')
        except sqlite3.Error as ex:
            click.echo('ERROR: {0}'.format(ex.message))


def print_columns():
    # Print out the list of columns.
    click.echo("Table 'symbols' has the following columns:")
    for col in COLUMNS:
        click.echo('{0}'.format(col[0]))


def list_columns(ctx, param, value):
    # Called when the --list-columns option is parsed.  Print out columns and 
    # stop any further processing.
    if not value or ctx.resilient_parsing:
        return
    print_columns()
    ctx.exit()


def print_results(result, columns, output, output_format):
    # Print out the results of a query to the specified output and using the
    # specified output format.
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


@main.command(short_help='query symbols of an ELF file using a SQL query syntax')
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
# arguments to the function.  Also note click will use the docstring as the
# full help text for the command.
def elfquery(input_file, query, output_format, output):
    """Query ELF symbols using a SQL-style query.

    Provide two arguments, a path to an ELF file and an optional SQL query to 
    make against the file.  The SQL query should be made against the table 
    'symbols' and it contains a row for each symbol (see the --list-columns
    option to list the available column names).

    If no query is provided then an interactive command loop will start where 
    multiple queries can be run successively.

    For example to list every symbol in order:

      legolas elfquery <file> "SELECT * FROM symbols ORDER BY Section, Number ASC"

    To select the name of each symbol from section '.symtab':

      legolas elfquery <file> "SELECT Name FROM symbols WHERE Section = '.symtab'"

    To do the same query but also restrict it to symbols with size > 256:

      legolas elfquery <file> "SELECT Name FROM symbols WHERE Section = '.symtab' AND Size > 256"

    To select all symbol data for symbols that are of type 'FUNC' or 'OBJECT':

      legolas elfquery <file> "SELECT * FROM symbols WHERE Type IN ('FUNC', 'OBJECT')"

    To select the name and size of the 5 largest symbols:

      legolas elfquery <file> "SELECT Name, Size FROM symbols ORDER BY Size DESC LIMIT 5"

    To list all variables in RAM sorted by size:

      legolas elfquery <file> "SELECT Size, Name, Value FROM symbols WHERE Type = 'OBJECT' ORDER BY Size ASC"

    To show the size of all values in the above RAM list:

      legolas elfquery <file> "SELECT SUM(Size) FROM symbols WHERE Type = 'OBJECT'"

    You can even do more advanced queries like counting how many unique Type
    values exist:

      legolas elfquery <file> "SELECT Type, COUNT(*) AS Count FROM symbols GROUP BY Type ORDER BY Count DESC"

    Any query supported by SQLite is possible against the symbols table.

    Results will be written as a friendly table format to standard output by
    default.  However look at the --output option to write results to a file,
    and the --output-format option to write results in a machine-friendly format
    like a comma or tab separated file.  Note that the output and output format
    options are ignored in interactive query mode.
    """
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
