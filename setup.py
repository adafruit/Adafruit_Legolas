from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

from Adafruit_Legolas import __version__


setup(name              = 'Adafruit_Legolas',
      version           = __version__,
      author            = 'Tony DiCola',
      author_email      = 'tdicola@adafruit.com',
      description       = 'Cross platform tool for manipulating ELF and other executable files for embedded systems.',
      license           = 'MIT',
      url               = 'https://github.com/adafruit/Adafruit_Adahex',
      entry_points      = {'console_scripts': ['legolas = Adafruit_Legolas.main:main']},
      install_requires  = ['Click', 'IntelHex', 'pyelftools'],
      packages          = find_packages())
