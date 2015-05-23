from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

from Adafruit_Legolas import __version__


setup(name              = 'Adafruit_Legolas',
      version           = __version__,
      author            = 'Tony DiCola',
      author_email      = 'tdicola@adafruit.com',
      description       = 'Command line tool to manipulate ELF and other binary & executable files for embedded systems.',
      license           = 'MIT',
      url               = 'https://github.com/adafruit/Adafruit_Legolas',
      entry_points      = {'console_scripts': ['legolas = Adafruit_Legolas.main:main']},
      install_requires  = ['Click', 'IntelHex', 'pyelftools', 'tabulate'],
      packages          = find_packages())
