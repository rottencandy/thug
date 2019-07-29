#!/usr/bin/env python
#
# Plugin.py
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA  02111-1307  USA


from .JSClass import JSClass


class Plugin(JSClass):
    def __init__(self, init = None):
        self._plugin = dict()

        if init is None:
            return

        for k, v in init.items():
            self._plugin[k] = v

    def __setitem__(self, key, value):
        self._plugin[key] = value

    def __getitem__(self, name):
        if name not in self._plugin:
            return None

        return self._plugin[name]

    def __delitem__(self, name):
        if name not in self._plugin:
            return

        del self._plugin[name]
