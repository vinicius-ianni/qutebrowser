# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2015 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Management of sessions - saved tabs/windows."""

import os
import os.path
import functools

from PyQt5.QtCore import pyqtSignal, QStandardPaths, QUrl, QObject, QPoint
from PyQt5.QtWidgets import QApplication
import yaml
try:
    from yaml import CSafeLoader as YamlLoader, CSafeDumper as YamlDumper
except ImportError:
    from yaml import SafeLoader as YamlLoader, SafeDumper as YamlDumper

from qutebrowser.browser import tabhistory
from qutebrowser.utils import standarddir, objreg, qtutils, log, usertypes
from qutebrowser.commands import cmdexc, cmdutils


completion_updater = None


class CompletionUpdater(QObject):

    """Simple QObject to be able to emit a signal if session files updated."""

    update = pyqtSignal()


class SessionError(Exception):

    """Exception raised when a session failed to load/save."""


class SessionNotFoundError(SessionError):

    """Exception raised when a session to be loaded was not found."""


def _get_session_path(name, check_exists=False):
    """Get the session path based on a session name or absolute path.

    Args:
        name: The name of the session.
        check_exists: Whether it should also be checked if the session exists.
    """
    base_path = os.path.join(standarddir.get(QStandardPaths.DataLocation),
                             'sessions')

    path = os.path.expanduser(name)
    if os.path.isabs(path) and ((not check_exists) or os.path.exists(path)):
        return path
    else:
        path = os.path.join(base_path, name + '.yml')
        if check_exists and not os.path.exists(path):
            raise SessionNotFoundError(path)
        else:
            return path


def exists(name):
    """Check if a named session exists."""
    try:
        _get_session_path(name, check_exists=True)
    except SessionNotFoundError:
        return False
    else:
        return True


def _save_tab(tab):
    """Get a dict with data for a single tab."""
    data = {'history': []}
    history = tab.page().history()
    for idx, item in enumerate(history.items()):
        qtutils.ensure_valid(item)
        item_data = {
            'url': bytes(item.url().toEncoded()).decode('ascii'),
            'title': item.title()
        }
        user_data = item.userData()
        if history.currentItemIndex() == idx:
            item_data['active'] = True
            if user_data is None:
                pos = tab.page().mainFrame().scrollPosition()
                data['zoom'] = tab.zoomFactor()
                data['scroll-pos'] = {'x': pos.x(), 'y': pos.y()}
        data['history'].append(item_data)

        if user_data is not None:
            pos = user_data['scroll-pos']
            data['zoom'] = user_data['zoom']
            data['scroll-pos'] = {'x': pos.x(), 'y': pos.y()}
    return data


def _save_all():
    """Get a dict with data for all windows/tabs."""
    data = {'windows': []}
    for win_id in objreg.window_registry:
        tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                    window=win_id)
        main_window = objreg.get('main-window', scope='window', window=win_id)
        win_data = {}
        win_data['geometry'] = bytes(main_window.saveGeometry())
        win_data['tabs'] = [_save_tab(tab) for tab in tabbed_browser.widgets()]
        data['windows'].append(win_data)
    return data


def save(name):
    """Save a named session."""
    path = _get_session_path(name)

    log.misc.debug("Saving session {} to {}...".format(name, path))
    data = _save_all()
    log.misc.vdebug("Saving data: {}".format(data))
    try:
        with qtutils.savefile_open(path) as f:
            yaml.dump(data, f, Dumper=YamlDumper, default_flow_style=False,
                      encoding='utf-8', allow_unicode=True)
    except (OSError, UnicodeEncodeError, yaml.YAMLError) as e:
        raise SessionError(e)
    else:
        completion_updater.update.emit()


def _load_tab(new_tab, data):
    """Load yaml data into a newly opened tab."""
    entries = []
    for histentry in data['history']:
        user_data = {}
        if 'zoom' in data:
            user_data['zoom'] = data['zoom']
        if 'scroll-pos' in data:
            pos = data['scroll-pos']
            user_data['scroll-pos'] = QPoint(pos['x'], pos['y'])
        active = histentry.get('active', False)
        entry = tabhistory.TabHistoryItem(
            QUrl.fromEncoded(histentry['url'].encode('ascii')),
            histentry['title'], active, user_data)
        entries.append(entry)
    try:
        new_tab.page().load_history(entries)
    except ValueError as e:
        raise SessionError(e)


def load(name):
    """Load a named session."""
    from qutebrowser.mainwindow import mainwindow
    path = _get_session_path(name, check_exists=True)
    try:
        with open(path, encoding='utf-8') as f:
            data = yaml.load(f, Loader=YamlLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise SessionError(e)
    log.misc.debug("Loading session {} from {}...".format(name, path))
    for win in data['windows']:
        win_id = mainwindow.MainWindow.spawn(geometry=win['geometry'])
        tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                    window=win_id)
        for tab in win['tabs']:
            new_tab = tabbed_browser.tabopen()
            _load_tab(new_tab, tab)


def delete(name):
    """Delete a session."""
    path = _get_session_path(name, check_exists=True)
    os.remove(path)
    completion_updater.update.emit()


def list_sessions():
    """Get a list of all session names."""
    base_path = os.path.join(standarddir.get(QStandardPaths.DataLocation),
                             'sessions')
    sessions = []
    for filename in os.listdir(base_path):
        base, ext = os.path.splitext(filename)
        if ext == '.yml':
            sessions.append(base)
    return sessions


@cmdutils.register(completion=[usertypes.Completion.sessions])
def session_load(name):
    """Load a session.

    Args:
        name: The name of the session.
    """
    try:
        load(name)
    except SessionNotFoundError:
        raise cmdexc.CommandError("Session {} not found!".format(name))
    except SessionError as e:
        raise cmdexc.CommandError("Error while loading session: {}".format(e))


@cmdutils.register(name=['session-save', 'w'],
                   completion=[usertypes.Completion.sessions])
def session_save(name='default'):
    """Save a session.

    Args:
        name: The name of the session.
    """
    try:
        save(name)
    except SessionError as e:
        raise cmdexc.CommandError("Error while saving session: {}".format(e))


@cmdutils.register(name='wq', completion=[usertypes.Completion.sessions])
def save_and_quit(name='default'):
    """Save open pages and quit.

    Args:
        name: The name of the session.
    """
    session_save(name)
    QApplication.closeAllWindows()


@cmdutils.register(completion=[usertypes.Completion.sessions])
def session_delete(name):
    """Delete a session.

    Args:
        name: The name of the session.
    """
    try:
        delete(name)
    except OSError as e:
        raise cmdexc.CommandError("Error while deleting session: {}".format(e))


def init(parent=None):
    """Initialize sessions."""
    global completion_updater
    session_path = os.path.join(standarddir.get(QStandardPaths.DataLocation),
                                'sessions')
    if not os.path.exists(session_path):
        os.mkdir(session_path)
    save_manager = objreg.get('save-manager')
    save_manager.add_saveable(
        'default-session', functools.partial(save, 'default'),
        config_opt=('general', 'save-session'))
    completion_updater = CompletionUpdater(parent)
