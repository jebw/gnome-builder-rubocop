#!/usr/bin/env python3

#
# __init__.py
#
# Copyright 2021 Jeremy Wilkins <jeb@jdwilkins.co.uk>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import gi
import json
import threading

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import Ide

_ = Ide.gettext


SEVERITY_MAP = {
    'info': Ide.DiagnosticSeverity.NOTE,
    'refactor': Ide.DiagnosticSeverity.NOTE,
    'convention': Ide.DiagnosticSeverity.NOTE,
    'warning': Ide.DiagnosticSeverity.WARNING,
    'error': Ide.DiagnosticSeverity.ERROR,
    'fatal': Ide.DiagnosticSeverity.FATAL
}

class RubocopDiagnosticProvider(Ide.Object, Ide.DiagnosticProvider):
    def create_launcher(self):
        context = self.get_context()
        srcdir = context.ref_workdir().get_path()
        launcher = None

        if context.has_project():
            build_manager = Ide.BuildManager.from_context(context)
            pipeline = build_manager.get_pipeline()
            if pipeline is not None:
                srcdir = pipeline.get_srcdir()
            runtime = pipeline.get_config().get_runtime()
            launcher = runtime.create_launcher()

        if launcher is None:
            launcher = Ide.SubprocessLauncher.new(0)

        launcher.set_flags(Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE)
        launcher.set_cwd(srcdir)

        return launcher

    def do_diagnose_async(self, file, file_content, lang_id, cancellable, callback, user_data):
        self.diagnostics_list = []
        task = Gio.Task.new(self, cancellable, callback)
        task.diagnostics_list = []

        launcher = self.create_launcher()
        srcdir = launcher.get_cwd()

        threading.Thread(target=self.execute, args=(task, launcher, srcdir, file, file_content),
                         name='rubocop-thread').start()

    def execute(self, task, launcher, srcdir, file, file_content):
        try:
            launcher.push_args(('rubocop', '--format', 'json'))

            if file_content:
                launcher.push_argv('--stdin')

            launcher.push_argv(file.get_path())

            sub_process = launcher.spawn()
            stdin = file_content.get_data().decode('UTF-8')
            success, stdout, stderr = sub_process.communicate_utf8(stdin, None)

            if not success:
                task.return_boolean(False)
                return

            results = json.loads(stdout)
            
            for result in results.get('files', []):
                for offense in result.get('offenses', []):
                    if 'location' not in offense:
                        continue
                    
                    location = offense['location']
                    
                    if 'start_line' not in location or 'start_column' not in location:
                        continue

                    start_line = max(location['start_line'] - 1, 0)
                    start_col = max(location['start_column'] - 1, 0)
                    start = Ide.Location.new(file, start_line, start_col)

                    end = None
                    if 'last_line' in location:
                        end_line = max(location['last_line'] - 1, 0)
                        end_col = max(location['last_column'], 0)
                        end = Ide.Location.new(file, end_line, end_col)
                    elif 'length' in location:
                        end_line = start_line
                        end_col = start_col + location['length']
                        end = Ide.Location.new(file, end_line, end_col)

                    message = offense['message']
                    severity = SEVERITY_MAP[offense['severity']]
                    diagnostic = Ide.Diagnostic.new(severity, message, start)
                    if end is not None:
                        range_ = Ide.Range.new(start, end)
                        diagnostic.add_range(range_)

                    task.diagnostics_list.append(diagnostic)
        except GLib.Error as err:
            task.return_error(err)
        except (json.JSONDecodeError, UnicodeDecodeError, IndexError) as e:
            task.return_error(GLib.Error('Failed to decode rubocop json: {}'.format(e)))
        else:
            task.return_boolean(True)

    def do_diagnose_finish(self, result):
        if result.propagate_boolean():
            diagnostics = Ide.Diagnostics()
            for diag in result.diagnostics_list:
                diagnostics.add(diag)
            return diagnostics

class RubocopPreferencesAddin(GObject.Object, Ide.PreferencesAddin):
    def do_load(self, preferences):
        self.rubocop = preferences.add_switch("code-insight",
                                              "diagnostics",
                                              "org.gnome.builder.plugins.rubocop",
                                              "enable-rubocop",
                                              None,
                                              "false",
                                              _("Rubocop"),
                                              _("Enable the use of Rubocop to provide linting for Ruby files"),
                                              # translators: these are keywords used to search for preferences
                                              _("ruby rubocop lint code"),
                                              500)

    def do_unload(self, preferences):
        preferences.remove_id(self.rubocop)
