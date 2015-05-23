# ELF file SQL-style query command.
#
# Query the attributes of an ELF file using a SQL query syntax.
#
# Author: Tony DiCola
import sqlite3
import sys

import click
from elftools.common.py3compat import bytes2str
from elftools.elf.dynamic import DynamicSection
from elftools.elf.elffile import ELFFile
from elftools.elf.descriptions import *
from elftools.elf.sections import SymbolTableSection
from elftools.elf.gnuversions import *

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
        """Perform SQL query against symbols and return result table."""
        return self.db.execute(query)


def list_columns(ctx, param, value):
    # Print out the list of columns and quit when --list-columns is invoked.
    if not value or ctx.resilient_parsing:
        return
    click.echo("Table 'symbols' has the following columns:")
    for col in COLUMNS:
        click.echo('{0}'.format(col[0]))
    ctx.exit()


@main.command(short_help='query symbols of an ELF file using a SQL query syntax')
# Take an ELF file path to query as input.
@click.argument('input_file',
                metavar='FILE',
                type=click.File('rb'))
# Also take a string to use as the query.
@click.argument('query',
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
# Add option to change the column delineator (default is comma).
@click.option('--delineator', '-d',
              default=',',
              help='delineator for result columns (default is comma)')
# Add option to output to a file (default is standard output).
@click.option('--output', '-o',
              type=click.File('wb'),
              default=sys.stdout,
              help='result file (default is standard output)')
# Define the command code.  Notice how click will send in parsed parameters as
# arguments to the function.  Also note click will use the docstring as the
# full help text for the command.
def elfquery(input_file, query, delineator, output):
    """Query ELF symbols using a SQL-style query.

    Provide two arguments, a path to an ELF file and a SQL query to make against
    the file.  The SQL query should be made against the table 'symbols' and it
    contains a row for each symbol (see the --list-columns option to list the
    available column names).

    For example to list every symbol in order:

      legolas elfquery <file> "SELECT * FROM symbols ORDER BY Section, Number ASC"

    Or to select the name of each symbol from section '.symtab':

      legolas elfquery <file> "SELECT Name FROM symbols WHERE Section = '.symtab'"

    Or to do the same query but also restrict it to symbols with size > 256:

      legolas elfquery <file> "SELECT Name FROM symbols WHERE Section = '.symtab' AND Size > 256"

    You can even do more advanced queries like counting how many unique Type
    values exist:

      legolas elfquery <file> "SELECT Type, COUNT(*) AS Count FROM symbols GROUP BY Type ORDER BY Count DESC"

    Any query supported by SQLite is possible against the symbols table.

    Results will be written to standard output by default, however they can be
    directed to a file with the --output option.  The results will contain a
    line for each row and all the of column values delineated by the specified
    delineator (default is a comma, see the --delineator option).
    """
    elfquery = ELFQuery(input_file)
    for row in elfquery.query(query):
        output.write(delineator.join(map(lambda x: str(x).strip(), row)))
        output.write('\n')
