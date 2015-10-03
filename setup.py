# Release procedure
#
# Prepare the release:
#
#  - run tests: tox
#  - fill the changelog in README.rst
#  - update version in setup.py
#  - set release date in the changelog in README.rst
#  - check that "python3 setup.py sdist" contains all files tracked by
#    the SCM (Mercurial): update MANIFEST.in if needed
#  - check README.rst formatting: rst2html README.rst README.html
#  - git commit -a
#  - git tag VERSION
#  - git push --tags
#  - git push
#
# Release the new version:
#
#  - python3 setup.py register sdist bdist_wheel upload
#
# After the release:
#
#  - increment version in setup.py
#  - git commit && git push
import sys

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

with open("README.rst") as fp:
    long_description = fp.read()

install_options = {
    "name": "sixer",
    "version": "0.8",
    "license": "Apache License 2.0",
    "author": 'Victor Stinner',
    "author_email": 'victor.stinner@gmail.com',

    "description": "Add Python 3 support to Python 2 applications using the six module.",
    "long_description": long_description,
    "url": "https://github.com/haypo/sixer",

    "classifiers": [
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
    ],
    "py_modules": ["sixer"],
    "entry_points": {'console_scripts': ['sixer=sixer:main']},
}

setup(**install_options)
