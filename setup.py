from setuptools import setup, find_packages

NAME = 'django-sugar-crm'
VERSION = '0.0.1'
PACKAGES = find_packages()
AUTHOR = 'an42rus'
URL = f'https://github.com/{AUTHOR}/{NAME}'

setup(
    name=NAME,
    version=VERSION,
    packages=PACKAGES,
    author=AUTHOR,
    url=URL,
    description='SugarCRM Python library with object api similar to Django ORM.'
)
