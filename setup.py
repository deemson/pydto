try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
import sys

sys.path.insert(0, '.')
version = __import__('pydto').__version__

with open('README.md') as f:
    long_description = f.read()

description = long_description.splitlines()[0].strip()

setup(
    name='pydto',
    url='https://github.com/deemson/pydto',
    download_url='https://github.com/deemson/pydto',
    version=version,
    description=description,
    long_description=long_description,
    license='MIT',
    platforms=['any'],
    py_modules=['pydto'],
    author='Dmitry Kurkin',
    author_email='dkurkin@toidev.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.1',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    install_requires=[
        'setuptools >= 0.6b1',
    ],
)