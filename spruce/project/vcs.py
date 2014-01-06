"""Version control system (VCS) tools."""

__copyright__ = "Copyright (C) 2014 Ivan D Vasin"
__docformat__ = "restructuredtext"

import os as _os
from pipes import quote as _shquote
import subprocess as _subprocess


def git_topdir(project_path='.'):
    testpath = _os.path.abspath(project_path)
    while True:
        if _os.path.isdir(_os.path.join(testpath, '.git')):
            return testpath

        if testpath == '/':
            break

        testpath, _ = _os.path.split(testpath)
    return None


def guess_vcs(project_path='.'):

    """Guess the VCS that is used by a particular project.

    :param str project_path:
        A file path to a project.

    :return:
        A best guess of the VCS that is used by the project at
        *project_path*.  One of the items in :const:`SYSTEMS`.  :obj:`None`
        if the project is unversioned or if its VCS is unknown.
    :rtype: :obj:`str` or null

    """

    if _os.path.isdir(project_path + '/.svn'):
        return 'svn'

    project_git_topdir = git_topdir(project_path)
    if project_git_topdir is not None:
        if _os.path.isdir(project_git_topdir + '/.git/svn'):
            return 'git-svn'
        return 'git'

    return None


def svn_last_changed_revision(project_path='.'):

    """
    The last Subversion revision in which a particular project was changed.

    :param str project_path:
        A file path to a project.

    :rtype: :obj:`int`

    :raise IncompatibleVcsError:
        Raised if the VCS of the project at ``project_path`` is not
        Subversion or git-svn.

    """

    SUPPORTED_SYSTEMS = ('svn', 'git-svn')

    vcs = guess_vcs(project_path)

    if vcs not in SUPPORTED_SYSTEMS:
        raise IncompatibleVcsError(vcs, SUPPORTED_SYSTEMS)

    if vcs == 'svn':
        svn_cmdargs = ('svn',)
    elif vcs == 'git-svn':
        svn_cmdargs = ('git', 'svn')
    else:
        assert False

    cmdargs = svn_cmdargs + ('info',)
    svn_proc = _subprocess.Popen(cmdargs, stdout=_subprocess.PIPE)
    grep_proc = _subprocess.Popen(('grep', 'Last Changed Rev'),
                                  stdin=svn_proc.stdout,
                                  stdout=_subprocess.PIPE)
    sed_proc = _subprocess.Popen(('sed', 's/[^0-9]//g'),
                                 stdin=grep_proc.stdout,
                                 stdout=_subprocess.PIPE)
    proc_output = sed_proc.communicate()[0]
    revision_str = proc_output.strip()

    # handle missing "Last Changed Rev"
    #     this is known to happen with git-svn before the project's second
    #     commit
    if revision_str == '':
        cmdargs = svn_cmdargs + ('log', '--incremental', '--limit', '1')
        svn_proc = _subprocess.Popen(cmdargs, stdout=_subprocess.PIPE)
        proc_output = svn_proc.communicate()[0]
        revision_str = proc_output.split()[1][1:]

    try:
        revision = int(revision_str)
    except ValueError:
        raise Error('invalid Subversion revision {!r} from `{}`'
                     .format(revision_str,
                             ' '.join(_shquote(arg) for arg in cmdargs)))

    return revision


SYSTEMS = ('git', 'git-svn', 'svn')
"""The known version control systems.

:type: =[:obj:`str`]

"""


def vcs_name(vcs):
    """The full name of a version control system.

    :param str vcs:
        One of the known :const:`SYSTEMS`.

    :rtype: :obj:`str`

    """
    vcs_names = {'git': 'Git', 'git-svn': 'git-svn', 'svn': 'Subversion'}
    return vcs_names[vcs]


class Error(RuntimeError):
    pass


class IncompatibleVcsError(Error):
    """
    An operation was attempted on an incompatible VCS.

    :param vcs:
        The incompatible VCS.  One of the items in :const:`SYSTEMS`.
        :obj:`None` if there is no VCS.
    :type vcs: :obj:`str` or null

    :param compatible_systems:
        The VCSes that are compatible.
    :type compatible_systems: ~[:obj:`str`]

    """
    def __init__(self, vcs, compatible_systems):
        compatible_systems_str = ', '.join(compatible_systems)
        if vcs is None:
            message = 'no VCS found; compatible systems are [{}]'\
                       .format(compatible_systems_str)
        else:
            message = 'incompatible VCS {!r}; compatible systems are [{}]'\
                       .format(vcs, compatible_systems_str)
        super(IncompatibleVcsError, self).__init__(message)
