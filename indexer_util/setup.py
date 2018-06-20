# coding: utf-8

from setuptools import setup, find_packages

NAME = "indexer_util"
VERSION = "1.0.0"

# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

REQUIRES = ['elasticsearch', 'jsmin']

setup(
    name=NAME,
    version=VERSION,
    description="Utilities for Data Explorer indexers",
    author_email="",
    url="",
    install_requires=REQUIRES,
    packages=find_packages(),
    include_package_data=True)
