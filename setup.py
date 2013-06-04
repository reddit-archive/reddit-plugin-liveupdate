#!/usr/bin/env python
from setuptools import setup, find_packages

setup(name='reddit_liveupdate',
    description='reddit live update threads',
    version='0.1',
    author='Neil Williams',
    author_email='neil@reddit.com',
    packages=find_packages(),
    install_requires=[
        'r2',
    ],
    entry_points={
        'r2.plugin':
            ['liveupdate = reddit_liveupdate:LiveUpdate']
    },
    zip_safe=False,
)
