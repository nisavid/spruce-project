#!/usr/bin/env python

"""Generate reStructuredText files for a project.

This script generates all of the reST (reStructuredText) files for a
project, overwriting existing ones.  It requires that the project is
installed.  It inspects the project's module hierarchy, generating reST
files as follows:

    * an :file:`index.rst` for the project that contains a table of
      contents with the project's top-level modules

    * a directory hierarchy that corresponds to the public package
      hierarchy

    * an :file:`index.rst` for each package in the public package
      hierarchy that contains

        * the package's docstring,

        * the docstrings of the public objects defined in the package's
          init module,

        * a table of contents with the package's included modules and
          public submodules

        * the docstrings of the package's included modules.

    * a :samp:`{M}.rst` for each public module *M*, placed inside the
      directory that corresponds to its containing package, that
      contains

        * the module's docstring,

        * the docstrings of the public objects defined in the module, and

        * the docstrings of the module's included modules.

If any of these parts fails---for example, due to modules that fail to
import or a code structure that confuses the script---then the script
will log the error, skip the failed part, and proceed with the other
parts.

"""

__copyright__ = "Copyright (C) 2014 Ivan D Vasin"
__credits__ = ["Ivan D Vasin"]
__docformat__ = "restructuredtext"

import abc as _abc
import argparse as _argparse
import logging as _logging
import os as _os
import re as _re
import runpy as _runpy
import sys as _sys
import traceback as _traceback

import spruce.introspect as _introspect
import spruce.pprint as _pprint


def main():

    loglevel = _logging.WARNING
    _logger.setLevel(level=loglevel)
    _log_formatter = _logging.Formatter(_LOGGING_FORMAT)
    _log_handler = _logging.StreamHandler()
    _log_handler.setFormatter(_log_formatter)
    _logger.addHandler(_log_handler)

    try:
        args = _parse_args()

        if args.debug:
            loglevel = _logging.DEBUG
        else:
            loglevel = _LOGLEVELS_BY_ARGVALUE[args.loglevel]
        _logger.setLevel(loglevel)

        _run(args)
    except _CriticalError as exc:
        _logger.critical(_format_exc(exc))
        _sys.exit(1)


def _ensure_project_output_dirs(docspec):

    def raise_error(message):
        raise _CriticalError('failed to create directory {!r}: {}'
                              .format(docspec.out_parentdirpath, message))

    def raise_notdir_error(file):
        raise_error('not a directory: {!r}'.format(file))

    project_out_dirpath = _os.path.dirname(docspec.out_filepath)
    if not _os.path.exists(project_out_dirpath):
        try:
            _os.makedirs(project_out_dirpath)
        except OSError as exc:
            match = _re.search(r'Not a directory: \'(.*)\'', str(exc))
            if match:
                filepath = match.group(1)
                if _os.path.sep in filepath:
                    filepath = _os.path.dirname(filepath)
                raise_notdir_error(filepath=filepath)
            else:
                raise_error(exc)
    elif not _os.path.isdir(project_out_dirpath):
        raise_notdir_error(filepath=project_out_dirpath)

    def ensure_child_output_dirs(docspec, parentdirpath):
        if not docspec.children:
            return
        dirpath = _os.path.join(parentdirpath, docspec.shortname)
        if not _os.path.exists(dirpath):
            try:
                _os.mkdir(dirpath)
            except OSError as exc:
                raise_error(exc)
        elif not _os.path.isdir(dirpath):
            raise_notdir_error(filepath=dirpath)
        for child_docspec in docspec.children:
            ensure_child_output_dirs(child_docspec, dirpath)

    for child_docspec in docspec.children:
        ensure_child_output_dirs(child_docspec, docspec.out_parentdirpath)


def _format_exc(exc, limit=None):
    message = str(exc)
    if _logger.isEnabledFor(_logging.DEBUG):
        message += '\n' + _traceback.format_exc(limit=limit)
    return message


def _generate_module_rest(docspec, pretend=False):

    output = []

    def doc_module_docspec(docspec, level=1, titlefunc=None,
                           module_isincluded=False):

        _logger.info('documenting module {}'.format(docspec.name))

        # FIXME: exclude attrs already documented in module docstring

        def doc_module_attr(attrname):

            def log_failed(exc):
                _log_failed_module_attr(docspec.name, attrname,
                                        message=_format_exc(exc))

            # determine directive
            attr = docspec.module_attr(attrname)
            try:
                metatype = attr.metatype
            except (AttributeError, ImportError, _introspect.InvalidObject) \
                   as exc:
                log_failed(exc)
                return
            if metatype == _introspect.Metatype.OLDSTYLE:
                directive = 'autodata'
            elif metatype == _introspect.Metatype.FUNCTION:
                directive = 'autofunction'
            elif metatype == _introspect.Metatype.CLASS:
                directive = 'autoclass'
            elif metatype == _introspect.Metatype.EXCEPTION:
                directive = 'autoexception'
            elif metatype == _introspect.Metatype.MODULE:
                # FIXME: inspect import
                if _introspect.module_path_isstandard(attr.name):
                    _log_skipped_module_attr(docspec.name, attrname,
                                             'it is a standard module')
                    return
                else:
                    try:
                        _introspect.module_from_object(attr).pyobject()
                    except ImportError:
                        directive = 'autodata'
                    else:
                        directive = 'automodule'
            else:
                _logger.warning('cannot determine metatype of attribute {} of'
                                 ' module {}; falling back to treating it as a'
                                 ' generic object'
                                 .format(attrname, docspec))
                directive = 'autodata'

            # document attribute
            output.extend(_rest_heading_lines(attrname, level=(level + 1)))
            output.append('.. {}:: {}.{}'.format(directive, docspec.name,
                                                 attrname))
            if directive in ['automodule', 'autoclass', 'autoexception']:
                autodoc_members_flags = ['members', 'undoc-members',
                                         'inherited-members']
                for flag in autodoc_members_flags:
                    output.append('   :{}:'.format(flag))
            output.append('')

        def doc_module_attrs():
            try:
                attrnames = docspec.module_attrnames
            except Exception as exc:
                _log_failed_module_attrs(docspec.name,
                                         message=_format_exc(exc))
            else:
                attrnames = [attrname for attrname in attrnames
                             if _should_doc_module_attr(docspec, attrname,
                                                        module_isincluded=
                                                            module_isincluded)]
                attrnames.sort(key=(lambda name: name.lower()))
                if attrnames:
                    _logger.info('documenting attributes of {}: {}'
                                  .format(docspec,
                                          ', '.join(attrname
                                                    for attrname
                                                    in attrnames)))
                for attrname in attrnames:
                    doc_module_attr(attrname)

        # determine title
        default_titlefunc = lambda docspec: docspec.name
        if not titlefunc:
            titlefunc = default_titlefunc
        try:
            title = titlefunc(docspec)
            title = title.rstrip('.')
        except:
            title = ''
        if not title:
            title = default_titlefunc(docspec)

        # document title and docstring
        output.extend(_rest_heading_lines(title, level=level))
        output.append('.. automodule:: {}'.format(docspec.name))
        output.append('')
        output.append('')

        # document children
        if not module_isincluded:
            children = list(docspec.children)
            children = [child for child in children
                        if _should_doc_module_docspec(child)]
            children.sort(key=(lambda docspec: docspec.name.lower()))
            if children:
                _logger.info('documenting children of {}: {}'
                              .format(docspec,
                                      ', '.join(str(child)
                                                for child in children)))
                output.extend(_rest_heading_lines('Submodules',
                                                  level=(level + 1)))
                output.append('.. toctree::')
                output.append('')
                for child in children:
                    assert child.name.startswith(docspec.name)
                    output.append('   {}'.format(child.reldocpath))
                output.append('')
                output.append('')

        # document attributes
        doc_module_attrs()

        # document included modules
        try:
            included_modules_docspecs = list(docspec.included_modules_docspecs)
        except (_introspect.InconsistentStructure, IOError) as exc:
            _log_failed_included_modules(docspec, message=_format_exc(exc))
        else:
            included_modules_docspecs = \
                [docspec_ for docspec_ in included_modules_docspecs
                 if _should_doc_module_docspec(docspec_,
                                               module_isincluded=True)]
            included_modules_docspecs.sort(key=(lambda docspec:
                                                    docspec.name.lower()))
            if included_modules_docspecs:
                _logger.info('documenting modules included in {}: {}'
                              .format(docspec,
                                      ', '.join(str(included_docspec)
                                                for included_docspec
                                                in included_modules_docspecs)))
            for included_module_docspec in included_modules_docspecs:
                doc_module_docspec(included_module_docspec,
                                   level=(level + 1),
                                   titlefunc=(lambda docspec:
                                                  docspec.shortdoc),
                                   module_isincluded=True)

    if pretend:
        output.append('')
        docpath = _os.path.sep.join(docspec.name.split('.'))
        output.append('{}.rst'.format(docpath))
        output.append('----')

    output.extend(_rest_file_header_lines(docspec))
    doc_module_docspec(docspec, titlefunc=(lambda docspec: docspec.name))

    if pretend:
        output.append('----')
        output.append('')

    if pretend:
        file_ = _sys.stdout
    else:
        file_ = open(docspec.out_filepath, 'w')

    for line in output:
        print >> file_, line

    if not pretend:
        file_.close()


def _generate_project_toplevel_rest(docspec, pretend=False):

    _logger.info('documenting project {}'.format(docspec.name))

    output = []
    output.extend(_rest_file_header_lines(docspec))
    output.append('`up to project list <../../>`_')
    output.append('')
    output.extend(_rest_heading_lines(docspec.name))
    output.append(docspec.docstring)
    output.append('')
    output.append('')

    descendants = list(docspec.top_interesting_descendants)
    descendants.sort(key=(lambda module_docspec: module_docspec.name.lower()))
    if descendants:
        output.extend(_rest_heading_lines('Modules', level=2))
        output.append('.. toctree::')
        output.append('')
        for module_docspec in descendants:
            module_rest_docpath = module_docspec.name.replace('.',
                                                              _os.path.sep)
            if module_docspec.children:
                module_rest_docpath = _os.path.join(module_rest_docpath,
                                                    'index')
            output.append('   {}'.format(module_rest_docpath))
        output.append('')
        output.append('')

    output.extend(_rest_heading_lines('Indices', level=2))
    output.append('* :ref:`genindex`')
    output.append('* :ref:`modindex`')
    output.append('* :ref:`search`')

    if pretend:
        file_ = _sys.stdout
    else:
        filepath = _os.path.join(docspec.out_parentdirpath, 'index.rst')
        file_ = open(filepath, 'w')

    for line in output:
        print >> file_, line

    if not pretend:
        file_.close()


def _generate_project_rests(docspec, pretend=False):
    _generate_project_toplevel_rest(docspec, pretend=pretend)
    for module_docspec in docspec.descendants:
        if module_docspec.skip:
            continue
        _generate_module_rest(module_docspec, pretend=pretend)


def _log_failed_included_modules(module_path, message):
    _log_failed_part('included modules of module {}'.format(module_path),
                     message=message)


def _log_failed_included_module(module_path, included_module_path, message):
    _log_failed_part('included module {} of module {}'
                      .format(included_module_path, module_path),
                     message=message)


def _log_failed_module(module_path, message):
    _log_failed_part('module {}'.format(module_path), message=message)


def _log_failed_module_attr(module_path, attrname, message):
    _log_failed_part('attribute {} of module {}'.format(attrname,
                                                        module_path),
                     message=message)


def _log_failed_module_attrs(module_path, message, attrnames=None):
    if attrnames:
        part_attrs = 'attributes [{}]'.format(', '.join(attrnames))
    else:
        part_attrs = 'attributes'
    _log_failed_part('{} of module {}'.format(part_attrs, module_path),
                     message=message)


def _log_failed_part(part, message):
    _logger.error('failed to document {}: {}'.format(part, message))


def _log_skipped_module(module_path, reason):
    _log_skipped_part('module {}'.format(module_path), reason=reason)


def _log_skipped_module_attr(module_path, attrname, reason):
    _log_skipped_part('attribute {} of module {}'
                       .format(attrname, module_path),
                      reason=reason)


def _log_skipped_part(part, reason):
    _logger.debug('skipping {} because {}'.format(part, reason))


def _parse_args():
    description = 'Generate reStructuredText files for a project.'
    parser = _argparse.ArgumentParser(description=description)
    parser.add_argument('path', metavar='PATH', nargs='?', default='.',
                        help='a file path to the project\'s root directory;'
                              ' default is %(default)s')
    parser.add_argument('--debug', action='store_true',
                        help='equivalent to --loglevel=debug')
    default_excluded_modules = ['setup']
    parser.add_argument('--excluded-modules', nargs='*',
                        default=default_excluded_modules,
                        help='top-level module names that should be excluded;'
                              ' default is {}'
                              .format(' '.join(default_excluded_modules)))
    parser.add_argument('--loglevel', choices=_LOGLEVELS_BY_ARGVALUE.keys(),
                        default='warning', help='the logging level')
    parser.add_argument('-o', '--output', default=_os.path.join('.', 'doc'),
                        help='a path to the output directory; default is'
                              ' %(default)s')
    parser.add_argument('-p', '--pretend', action='store_true',
                        help='do not write output files, but show what would'
                              ' be written')
    default_src = ['.']
    parser.add_argument('-s', '--src', nargs='*', default=default_src,
                        help='a relative path to the project\'s source code'
                              ' directory; default is {}'
                              .format(' '.join(default_src)))
    return parser.parse_args()


def _rest_file_header_lines(docspec):
    header = []
    header.append('.. highlight:: python')
    header.append('   :linenothreshold: 5')
    header.append('')
    return header


def _rest_heading_lines(text, level=1):

    assert level >= 1

    if level == 1:
        line_char = '#'
    elif level == 2:
        line_char = '*'
    elif level == 3:
        line_char = '='
    elif level == 4:
        line_char = '-'
    elif level == 5:
        line_char = '^'
    elif level == 6:
        line_char = '"'
    else:
        line_char = '+'

    line = line_char * len(text)
    return [line, text, line]


def _run(args):
    project_docspec = _ProjectDocSpec(args.path, args.output,
                                      src_dirnames=args.src)
    project_docspec.excluded_modules_names.extend(args.excluded_modules)
    if not args.pretend:
        _ensure_project_output_dirs(project_docspec)
    _generate_project_rests(project_docspec, pretend=args.pretend)


def _should_doc_module_docspec(docspec, module_isincluded=False):

    def log_skip(reason):
        _log_skipped_module(docspec.name, reason=reason)

    if not module_isincluded:
        if docspec.module_isprivate:
            log_skip(reason='it is private')
            return False

        if docspec.module_isstandard:
            log_skip(reason='it is in the Python standard library')
            return False

    return True


def _should_doc_module_attr(module_docspec, attrname, module_isincluded=False):

    module_path = module_docspec.name

    def log_skip(reason):
        _log_skipped_module_attr(module_path, attrname, reason=reason)

    if attrname in dir(__builtins__):
        log_skip(reason='it is a built-in')
        return False

    if attrname.startswith('_'):
        log_skip(reason='it is private')
        return False
    if attrname == 'extension':
        log_skip(reason='it is defined for all modules')
        return False

    try:
        included_modules_docspecs = \
            list(module_docspec.included_modules_docspecs)
        descendants_included_modules_docspecs = \
            list(module_docspec.descendants_included_modules_docspecs)
    except IOError:
        pass
    else:
        for included_module_docspec in included_modules_docspecs:
            if included_module_docspec.parent == module_docspec \
                   and attrname == included_module_docspec.shortname:
                log_skip(reason='it is an included module')
                return False

        # skip attributes defined in included modules
        # FIXME: do not skip attributes that are defined in included modules
        #     only by being imported from a higher-up module
        for included_module_docspec \
                in included_modules_docspecs \
                   + descendants_included_modules_docspecs:
            try:
                included_module_attrnames = \
                    included_module_docspec.module_attrnames
            except (AttributeError, ImportError, _introspect.InvalidObject):
                continue
            if attrname in included_module_attrnames:
                log_skip(reason='it will be documented as part of the included'
                                 ' module {}'
                                 .format(included_module_docspec.name))
                return False

    if not module_isincluded:
        if any(attrname == child.shortname
               for child in module_docspec.children):
            log_skip(reason='it is a submodule')
            return False

    # FIXME: skip attributes of standard modules

    return True


class _DocSpec(object):

    __metaclass__ = _abc.ABCMeta

    def __init__(self, src_filepath, out_parentdirpath, parent=None):
        self._ancestor_included_modulepaths_ = None
        self._descendants = None
        self._out_dirpath = _os.path.normpath(out_parentdirpath)
        self._parent = parent
        self._root = None
        self._src_filepath = _os.path.normpath(src_filepath)

    def __repr__(self):
        return '{}({!r}, src_filepath={!r}, out_parentdirpath={!r})'\
                .format(self.__class__.__name__, self.name, self.src_filepath,
                        self.out_parentdirpath)

    def __str__(self):
        return self.name

    @_abc.abstractproperty
    def children(self):
        pass

    @property
    def descendants(self):
        if not self._descendants:
            descendants = []
            for child in self.children:
                descendants.append(child)
                descendants.extend(child.descendants)
            self._descendants = descendants
        return self._descendants

    @property
    def docpath(self):
        parentdocpath = _os.path.relpath(self.out_parentdirpath,
                                         self.root.out_parentdirpath)
        return _os.path.normpath(_os.path.join(parentdocpath, self.reldocpath))

    @_abc.abstractproperty
    def docstring(self):
        pass

    @_abc.abstractproperty
    def included_modules_paths(self):
        pass

    @_abc.abstractproperty
    def included_modules_docspecs(self):
        pass

    @_abc.abstractproperty
    def isproject(self):
        pass

    @_abc.abstractproperty
    def name(self):
        pass

    @property
    def out_parentdirpath(self):
        return self._out_dirpath

    @property
    def out_filepath(self):
        return _os.path.join(self.root.out_parentdirpath,
                             self.docpath + '.rst')

    @property
    def parent(self):
        return self._parent

    @property
    def reldocpath(self):
        if self.isproject:
            relpath = 'index'
        elif self.children:
            relpath = _os.path.join(self.shortname, 'index')
        else:
            relpath = self.shortname
            if relpath == 'index':
                relpath += '_'
        return relpath

    @property
    def root(self):
        if self._root is None:
            if not self.parent:
                root = self
            else:
                root = self.parent.root
            self._root = root
        return self._root

    @_abc.abstractproperty
    def shortdoc(self):
        pass

    @_abc.abstractproperty
    def shortname(self):
        pass

    @property
    def skip(self):
        return self._skip

    @skip.setter
    def skip(self, skip):
        self._skip = skip

    @property
    def src_filepath(self):
        return self._src_filepath

    @property
    def _ancestor_included_modulepaths(self):
        if self._ancestor_included_modulepaths_ is None:
            self._ancestor_included_modulepaths_ = []
            ancestor = self.parent
            while ancestor:
                self._ancestor_included_modulepaths_ += \
                    ancestor.included_modules_paths
                ancestor = ancestor.parent
        return self._ancestor_included_modulepaths_


class _ModuleDocSpec(_DocSpec):

    def __init__(self, src_filepath, out_parentdirpath, parent):
        super(_ModuleDocSpec, self).__init__(src_filepath, out_parentdirpath,
                                             parent=parent)
        self._children = None
        self._descendants_included_modules_docspecs = None
        self._included_modules_paths = None
        self._included_modules_docspecs = None
        self._module_ = None
        self.skip = False

    @property
    def children(self):
        if self._children is None:
            if self._module.ispackage:
                self._children = \
                    [_ModuleDocSpec(module.filepath,
                                    _os.path.join(self.out_parentdirpath,
                                                  self.shortname),
                                    parent=self)
                     for module
                     in self._module.submodules(include_packages=True)
                     if module.path not in self.included_modules_paths
                        and module.path
                            not in self._ancestor_included_modulepaths]
            else:
                self._children = []
        return self._children

    @property
    def descendants_included_modules_docspecs(self):
        if self._descendants_included_modules_docspecs is None:
            modules = []
            for child in self.children:
                try:
                    modules.extend(child.included_modules_docspecs)
                except IOError as exc:
                    _log_failed_included_modules(child.name,
                                                 message=_format_exc(exc))
                modules.extend(child.descendants_included_modules_docspecs)
            self._descendants_included_modules_docspecs = modules
        return self._descendants_included_modules_docspecs

    @property
    def docstring(self):
        return self._module.docstring

    @property
    def included_modules_docspecs(self):
        for path in self.included_modules_paths:
            try:
                module = self._module.module_intree(path,
                                                    fallback_outoftree=True)
            except ImportError as exc:
                _log_failed_included_module(self.name, path,
                                            message=_format_exc(exc))
                continue
            if module:
                yield _ModuleDocSpec(module.filepath, self.out_parentdirpath,
                                     parent=self)
            else:
                _log_failed_included_module(self.name, path,
                                            message='cannot find module')

    @property
    def included_modules_paths(self):
        if self._included_modules_paths is None:
            self._included_modules_paths = \
                self._module.included_modules_paths(toabs=True)
        return self._included_modules_paths

    @property
    def isproject(self):
        return False

    def module_attr(self, name):
        return self._module.attr(name)

    @property
    def module_attrnames(self):
        return self._module.attrnames

    @property
    def module_isprivate(self):
        return self._module.isprivate

    @property
    def module_isstandard(self):
        return self._module.isstandard

    @property
    def name(self):
        return self._module.path

    @property
    def shortdoc(self):
        return self._module.shortdoc

    @property
    def shortname(self):
        return self._module.name

    @property
    def _module(self):
        if self._module_ is None:
            self._module_ = \
                _introspect.module_from_filepath(self.src_filepath)
            # XXX: the in-tree loading mechanism doesn't play well with
            #     implicit relative imports, so we avoid it altogether here
            # TODO: remove this once most of our code does not use implicit
            #     relative imports
            self._module.load_tree_filepath = None
        return self._module_


class _ProjectDocSpec(_DocSpec):

    def __init__(self, project_dirpath, out_parentdirpath, src_dirnames):
        super(_ProjectDocSpec, self).__init__(src_filepath=project_dirpath,
                                              out_parentdirpath=
                                                  out_parentdirpath)
        self._children = None
        self._docstring = None
        self._excluded_modules_names = []
        self._interesting_descendants = None
        self._sphinx_settings_ = None
        self._src_dirnames = src_dirnames
        self._top_interesting_descendants = None

    @property
    def children(self):
        if self._children is None:
            def src_dirpath(dirname):
                return _os.path.normpath(_os.path.join(self.src_filepath,
                                                       dirname))

            def module_filepath(module):
                return module.filepath \
                       if not module.ispackage else module.dirpath

            self._children = \
                [_ModuleDocSpec(module_filepath(module),
                                self.out_parentdirpath, parent=self)
                 for module
                 in sum((_introspect.top_modules
                          (src_dirpath(dirname), include_packages=True,
                           excluded_names=self.excluded_modules_names)
                         for dirname in self.src_dirnames),
                        [])]
        return self._children

    @property
    def docstring(self):
        if self._docstring is None:
            self._docstring = ''
            for descendant in self.top_interesting_descendants:
                if (descendant.name == self.shortname
                    or descendant.name
                       == 'spruce.{}'.format(self.shortname)):
                    # ???: is there a better way to do this
                    #     try/except/log/skip?
                    try:
                        self._docstring = descendant.docstring
                    except Exception as exc:
                        _log_failed_module(descendant.name,
                                           message=_format_exc(exc))
                        descendant.skip = True
                        continue
        return self._docstring

    @property
    def excluded_modules_names(self):
        return self._excluded_modules_names

    @property
    def included_modules_docspecs(self):
        return []

    @property
    def included_modules_paths(self):
        return []

    @property
    def interesting_descendants(self):
        if self._interesting_descendants is None:
            descendants = []
            for descendant in self.descendants:
                if self._descendant_is_interesting(descendant):
                    descendants.append(descendant)
                descendants.extend(descendant.interesting_descendants)
            self._interesting_descendants = descendants
        return self._interesting_descendants

    @property
    def isproject(self):
        return True

    @property
    def name(self):
        return self._sphinx_settings['project']

    @property
    def shortdoc(self):
        blocks = _pprint.split_blocks(self.docstring)
        if blocks:
            return blocks[0]
        else:
            return ''

    @property
    def shortname(self):
        strippable_prefix = 'spruce-'
        if self.name.startswith(strippable_prefix):
            return self.name[len(strippable_prefix):]
        else:
            return self.name

    @property
    def src_dirnames(self):
        return self._src_dirnames

    @property
    def top_interesting_descendants(self):
        if self._top_interesting_descendants is None:
            descendants = []
            for child in self.children:
                if self._descendant_is_interesting(child):
                    descendants.append(child)
                else:
                    descendants.extend(child.children)
            self._top_interesting_descendants = descendants
        return self._top_interesting_descendants

    def _descendant_is_interesting(self, descendant):
        return descendant.name != 'nisavid'

    @property
    def _sphinx_settings(self):
        if self._sphinx_settings_ is None:
            sphinx_conf = _os.path.join(self.out_parentdirpath, 'conf.py')
            if not _os.path.exists(sphinx_conf):
                raise _CriticalError('no Sphinx config found at {!r}'
                                      .format(sphinx_conf))
            self._sphinx_settings_ = _runpy.run_path(sphinx_conf)
        return self._sphinx_settings_


class _CriticalError(RuntimeError):
    """An error after which it is unsafe or not useful to continue."""
    pass


_logger = _logging.getLogger('project-doc-rest-gen')


_LOGGING_FORMAT = '%(levelname)s: %(message)s'


_LOGLEVELS_BY_ARGVALUE = {'critical': _logging.CRITICAL,
                          'error': _logging.ERROR,
                          'warning': _logging.WARNING,
                          'info': _logging.INFO,
                          'debug': _logging.DEBUG,
                          }


if __name__ == '__main__':
    main()
