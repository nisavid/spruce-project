#!/usr/bin/env python

__copyright__ = "Copyright (C) 2013 Ivan D Vasin and Cogo Labs"
__credits__ = ["Ivan D Vasin"]
__maintainer__ = "Ivan D Vasin"
__email__ = "nisavid@gmail.com"
__docformat__ = "restructuredtext"

from setuptools import find_packages as _find_packages, setup as _setup


# basics ----------------------------------------------------------------------

NAME_NOPREFIX = 'project'

NAME = 'nisavid-' + NAME_NOPREFIX

VERSION = '0'

SITE_URI = ''

DESCRIPTION = 'Project inspection, management, and administration.'

LONG_DESCRIPTION = DESCRIPTION + '''

These tools cover operations on projects from inception through
building, including creating, fetching, inspecting, editing, version
control, and building.
'''

LICENSE = 'LGPLv3'

TROVE_CLASSIFIERS = \
    ('Development Status :: 5 - Production/Stable',
     'Intended Audience :: Developers',
     'License :: OSI Approved :: GNU Lesser General Public License v3'
      ' (LGPLv3)',
     'Operating System :: POSIX',
     'Programming Language :: Python :: 2.7',
     'Topic :: Software Development :: Documentation',
     'Topic :: Software Development :: Libraries :: Python Modules',
     'Topic :: Software Development :: Version Control',
     'Topic :: System :: Archiving :: Packaging',
     )


# dependencies ----------------------------------------------------------------

SETUP_DEPS = ()

INSTALL_DEPS = ('gitpython', 'nisavid-introspect', 'nisavid-pprint')

EXTRAS_DEPS = {}

TESTS_DEPS = ()

DEPS_SEARCH_URIS = ()


# packages --------------------------------------------------------------------

PARENT_NAMESPACE_PKG = 'nisavid'

ROOT_PKG = '.'.join((PARENT_NAMESPACE_PKG, NAME_NOPREFIX))

NAMESPACE_PKGS = (PARENT_NAMESPACE_PKG,)

SCRIPTS_PKG = '.'.join((ROOT_PKG, 'scripts'))

TESTS_PKG = '.'.join((ROOT_PKG, 'tests'))


# entry points ----------------------------------------------------------------

STD_SCRIPTS_PKG_COMMANDS = {'project-doc-gen-rest': 'doc_gen_rest'}

COMMANDS = {cmd: '{}.{}:{}'.format(SCRIPTS_PKG,
                                   script if isinstance(script, basestring)
                                          else script[0],
                                   'main' if isinstance(script, basestring)
                                          else script[1])
            for cmd, script in STD_SCRIPTS_PKG_COMMANDS.items()}

ENTRY_POINTS = {'console_scripts': ['{} = {}'.format(name, funcpath)
                                    for name, funcpath in COMMANDS.items()]}


if __name__ == '__main__':
    _setup(name=NAME,
           version=VERSION,
           url=SITE_URI,
           description=DESCRIPTION,
           long_description=LONG_DESCRIPTION,
           author=', '.join(__credits__),
           maintainer=__maintainer__,
           maintainer_email=__email__,
           license=LICENSE,
           classifiers=TROVE_CLASSIFIERS,
           setup_requires=SETUP_DEPS,
           install_requires=INSTALL_DEPS,
           extras_require=EXTRAS_DEPS,
           tests_require=TESTS_DEPS,
           dependency_links=DEPS_SEARCH_URIS,
           namespace_packages=NAMESPACE_PKGS,
           packages=_find_packages(),
           test_suite=TESTS_PKG,
           include_package_data=True,
           entry_points=ENTRY_POINTS)