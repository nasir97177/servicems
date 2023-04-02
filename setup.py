# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open('requirements.txt') as f:
	install_requires = f.read().strip().split('\n')

# get version from __version__ variable in servicems/__init__.py
from servicems import __version__ as version

setup(
	name='servicems',
	version=version,
	description='Service Management System for ERPNext',
	author='Aakvatech Limited',
	author_email='info@aakvatech.com',
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
