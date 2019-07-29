#!/usr/bin/env python
#
# DFT.py
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

import os
import re
import string
import base64
import random
# import types
import logging

import bs4
import six
import six.moves.urllib.parse as urlparse
import cchardet
import pylibemu

from cssutils.parse import CSSParser

from thug.ActiveX.ActiveX import _ActiveXObject
from thug.DOM.W3C import w3c

log = logging.getLogger("Thug")


class DFT(object):
    javascript     = ('javascript', )
    vbscript       = ('vbs', 'vbscript', 'visualbasic')

    # Some event types are directed at the browser as a whole, rather than at
    # any particular document element. In JavaScript, handlers for these events
    # are registered on the Window object. In HTML, we place them on the <body>
    # tag, but the browser registers them on the Window. The following is the
    # complete list of such event handlers as defined by the draft HTML5
    # specification:
    #
    # onafterprint      onfocus         ononline        onresize
    # onbeforeprint     onhashchange    onpagehide      onstorage
    # onbeforeunload    onload          onpageshow      onundo
    # onblur            onmessage       onpopstate      onunload
    # onerror           onoffline       onredo
    window_events = ('abort',
                     'afterprint',
                     'beforeprint',
                     'beforeunload',
                     'blur',
                     'error',
                     'focus',
                     'hashchange',
                     'load',
                     'message',
                     'offline',
                     'online',
                     'pagehide',
                     'pageshow',
                     'popstate',
                     'redo',
                     'resize',
                     'storage',
                     'undo',
                     'unload')

    window_on_events = ['on' + e for e in window_events]

    window_storage_events = ('storage', )
    window_on_storage_events = ['on' + e for e in window_storage_events]
    _on_events = window_on_events + window_on_storage_events

    user_detection_events = ('mousemove', 'scroll', )
    on_user_detection_events = ['on' + e for e in user_detection_events]

    def __init__(self, window, **kwds):
        self.window            = window
        self.window.doc.DFT    = self
        self.anchors           = list()
        self.forms             = kwds['forms'] if 'forms' in kwds else list()
        self._context          = None
        log.DFT                = self
        self._init_events()
        self._init_pyhooks()

    def _init_events(self):
        self.listeners = list()

        # Events are handled in the same order they are inserted in this list
        self.handled_events = ['load', 'mousemove']

        for event in log.ThugOpts.events:
            self.handled_events.append(event)

        self.handled_on_events = ['on' + e for e in self.handled_events]
        self.dispatched_events = set()

    def _init_pyhooks(self):
        hooks = log.PyHooks.get('DFT', None)
        if hooks is None:
            return

        for label, hook in hooks.items():
            name   = "{}_hook".format(label)
            # _hook  = hook.im_func if hook.im_self else hook
            _hook = six.get_method_function(hook) if six.get_method_self(hook) else hook
            # method = types.MethodType(_hook, self, DFT)
            method = six.create_bound_method(_hook, DFT)
            setattr(self, name, method)

    def __enter__(self):
        return self

    def __exit__(self, _type, value, traceback):
        pass

    @property
    def context(self):
        if self._context is None:
            self._context = self.window.context

        return self._context

    def build_shellcode(self, s):
        i  = 0
        sc = list()

        while i < len(s):
            if s[i] == '"':
                i += 1
                continue

            if s[i] == '%':
                if (i + 6) <= len(s) and s[i + 1] == 'u':
                    currchar = int(s[i + 2: i + 4], 16)
                    nextchar = int(s[i + 4: i + 6], 16)
                    sc.append(chr(nextchar))
                    sc.append(chr(currchar))
                    i += 6
                elif (i + 3) <= len(s) and s[i + 1] == 'u':
                    currchar = int(s[i + 2: i + 4], 16)
                    sc.append(chr(currchar))
                    i += 3
                else:
                    sc.append(s[i])
                    i += 1
            else:
                sc.append(s[i])
                i += 1

        return ''.join(sc)

    def check_URLDownloadToFile(self, emu, snippet):
        profile = emu.emu_profile_output

        while True:
            offset = profile.find('URLDownloadToFile')
            if offset < 0:
                break

            profile = profile[offset:]

            p = profile.split(';')
            if len(p) < 2:
                profile = profile[1:]
                continue

            p = p[1].split('"')
            if len(p) < 3:
                profile = profile[1:]
                continue

            url = p[1]
            if url in log.ThugLogging.shellcode_urls:
                return

            try:
                if self.window._navigator.fetch(url, redirect_type = "URLDownloadToFile", snippet = snippet) is None:
                    log.ThugLogging.add_behavior_warn('[URLDownloadToFile] Fetch failed', snippet = snippet)

                log.ThugLogging.shellcode_urls.add(url)
            except Exception:
                log.ThugLogging.add_behavior_warn('[URLDownloadToFile] Fetch failed', snippet = snippet)

            profile = profile[1:]

    def check_WinExec(self, emu, snippet):
        profile = emu.emu_profile_output

        while True:
            offset = profile.find('WinExec')
            if offset < 0:
                break

            profile = profile[offset:]

            p = profile.split(';')
            if not p:
                profile = profile[1:]
                continue

            s = p[0].split('"')
            if len(s) < 2:
                profile = profile[1:]
                continue

            url = s[1]
            if not url.startswith("http"):
                profile = profile[1:]
                continue

            if url in log.ThugLogging.shellcode_urls:
                return

            try:
                if self.window._navigator.fetch(url, redirect_type = "WinExec", snippet = snippet) is None:
                    log.ThugLogging.add_behavior_warn('[WinExec] Fetch failed', snippet = snippet)

                log.ThugLogging.shellcode_urls.add(url)
            except Exception:
                log.ThugLogging.add_behavior_warn('[WinExec] Fetch failed', snippet = snippet)

            profile = profile[1:]

    def check_shellcode(self, shellcode):
        if not shellcode:
            return

        enc = cchardet.detect(shellcode)
        if enc['encoding']:
            try:
                shellcode = shellcode.decode(enc['encoding']).encode('latin1')
            except Exception:
                pass
        else:
            shellcode = shellcode.encode('latin1')

        try:
            sc = self.build_shellcode(shellcode)
        except Exception:
            sc = shellcode

        emu = pylibemu.Emulator(enable_hooks = False)
        emu.run(sc)

        if emu.emu_profile_output:
            # try:
            #    encoded_sc = shellcode.encode('unicode-escape')
            # except:  # pylint:disable=bare-except
            #    encoded_sc = "Unable to encode shellcode"

            snippet = log.ThugLogging.add_shellcode_snippet(sc,
                                                            "Assembly",
                                                            "Shellcode",
                                                            method = "Static Analysis")

            log.ThugLogging.add_behavior_warn(description = "[Shellcode Profile] {}".format(emu.emu_profile_output),
                                              snippet     = snippet,
                                              method      = "Static Analysis")

            self.check_URLDownloadToFile(emu, snippet)
            self.check_WinExec(emu, snippet)

        self.check_url(sc, shellcode)
        emu.free()

    def check_url(self, sc, shellcode):
        from .Window import Window

        schemes = []
        for scheme in ('http://', 'https://'):
            if scheme in sc:
                schemes.append(scheme)

        for scheme in schemes:
            offset = sc.find(scheme)
            if offset == -1:
                continue

            url = sc[offset:]
            url = url.split()[0]
            if url.endswith("'") or url.endswith('"'):
                url = url[:-1]

            if not url:
                continue

            i = 0

            while i < len(url):
                if not url[i] in string.printable:
                    break
                i += 1

            url = url[:i]

            if url in log.ThugLogging.retrieved_urls:
                return

            try:
                encoded_sc = shellcode.encode('unicode-escape')
            except Exception:
                encoded_sc = "Unable to encode shellcode"

            snippet = log.ThugLogging.add_shellcode_snippet(encoded_sc,
                                                            "Assembly",
                                                            "Shellcode",
                                                            method = "Static Analysis")

            log.ThugLogging.add_behavior_warn(description = "[Shellcode Analysis] URL Detected: {}".format(url),
                                              snippet     = snippet,
                                              method      = "Static Analysis")

            if url in log.ThugLogging.shellcode_urls:
                return

            try:
                response = self.window._navigator.fetch(url, redirect_type = "URL found")
                log.ThugLogging.shellcode_urls.add(url)
            except Exception:
                return

            if response is None or not response.ok:
                return

            doc    = w3c.parseString(response.content)
            window = Window(self.window.url, doc, personality = log.ThugOpts.useragent)

            dft = DFT(window)
            dft.run()

    def check_shellcodes(self):
        while True:
            try:
                shellcode = log.ThugLogging.shellcodes.pop()
                self.check_shellcode(shellcode)
            except KeyError:
                break

    def get_evtObject(self, elem, evtType):
        from thug.DOM.W3C.Events.Event import Event
        from thug.DOM.W3C.Events.MouseEvent import MouseEvent
        from thug.DOM.W3C.Events.HTMLEvent import HTMLEvent

        evtObject = None

        if evtType in MouseEvent.EventTypes:
            evtObject = MouseEvent()

        if evtType in HTMLEvent.EventTypes:
            evtObject = HTMLEvent()

        if evtObject is None:
            return None

        evtObject._target = elem
        evtObject.eventPhase = Event.AT_TARGET
        evtObject.currentTarget = elem
        return evtObject

    # Events handling
    def handle_element_event(self, evt):
        from thug.DOM.W3C.Events.Event import Event

        for (elem, eventType, listener, capture) in self.listeners:  # pylint:disable=unused-variable
            if getattr(elem, 'name', None) is None:
                continue

            if elem.name in ('body', ):
                continue

            evtObject = Event()
            evtObject._type = eventType

            if eventType in (evt, ):
                if (elem._node, evt) in self.dispatched_events:
                    continue

                elem._node.dispatchEvent(evtObject)
                self.dispatched_events.add((elem._node, evt))

    def handle_window_storage_event(self, onevt, evtObject):
        if onevt in self.handled_on_events:
            handler = getattr(self.window, onevt, None)
            if handler:
                handler(evtObject)

    def run_event_handler(self, handler, evtObject):
        if log.ThugOpts.Personality.isIE() and log.ThugOpts.Personality.browserMajorVersion < 9:
            self.window.event = evtObject
            handler()
        else:
            handler(evtObject)

    def handle_window_event(self, onevt):
        if onevt in self.handled_on_events and onevt not in self.window_on_storage_events:
            count = random.randint(30, 50) if onevt in self.on_user_detection_events else 1

            while count > 0:
                evtObject = self.get_evtObject(self.window, onevt[2:])

                handler = getattr(self.window, onevt, None)
                if handler:
                    self.run_event_handler(handler, evtObject)

                    if onevt in self.window_on_events:
                        if (self.window, onevt[2:], handler) in self.dispatched_events:
                            return

                    self.dispatched_events.add((self.window, onevt[2:], handler))

                count -= 1

    def handle_document_event(self, onevt):
        if onevt in self.handled_on_events:
            count = random.randint(30, 50) if onevt in self.on_user_detection_events else 1

            while count > 0:
                evtObject = self.get_evtObject(self.window.doc, onevt[2:])

                handler = getattr(self.window.doc, onevt, None)
                if handler:
                    self.run_event_handler(handler, evtObject)

                count -= 1

        # if not getattr(self.window.doc.tag, '_listeners', None):
        #    return

        if '_listeners' not in self.window.doc.tag.__dict__:
            return

        for (eventType, listener, capture) in self.window.doc.tag._listeners:  # pylint:disable=unused-variable
            if eventType not in (onevt[2:], ):
                continue

            count = random.randint(30, 50) if onevt in self.on_user_detection_events else 1

            while count > 0:
                evtObject = self.get_evtObject(self.window.doc, eventType)
                self.run_event_handler(listener, evtObject)
                count -= 1

    def _build_event_handler(self, ctx, h):
        # When an event handler is registered by setting an HTML attribute
        # the browser converts the string of JavaScript code into a function.
        # Browsers other than IE construct a function with a single argument
        # named `event'. IE constructs a function that expects no argument.
        # If the identifier `event' is used in such a function, it refers to
        # `window.event'. In either case, HTML event handlers can refer to
        # the event object as `event'.
        if log.ThugOpts.Personality.isIE():
            return ctx.eval("(function() { with(document) { with(this.form || {}) { with(this) { event = window.event; %s } } } }) " % (h, ))

        return ctx.eval("(function(event) { with(document) { with(this.form || {}) { with(this) { %s } } } }) " % (h, ))

    def build_event_handler(self, ctx, h):
        try:
            return self._build_event_handler(ctx, h)
        except SyntaxError as e: # pragma: no cover
            log.info("[SYNTAX ERROR][build_event_handler] %s", str(e))
            return None

    def set_event_handler_attributes(self, elem):
        try:
            attrs = elem.attrs
        except Exception:
            return

        if 'language' in list(attrs.keys()) and not attrs['language'].lower() in ('javascript', ):
            return

        for evt, h in attrs.items():
            if evt not in self.handled_on_events:
                continue

            self.attach_event(elem, evt, h)

    def attach_event(self, elem, evt, h):
        handler = None

        if isinstance(h, six.string_types):
            handler = self.build_event_handler(self.context, h)
            # log.JSEngine.collect()
        elif log.JSEngine.isJSFunction(h):
            handler = h
        else:
            try:
                handler = getattr(self.context.locals, h, None)
            except Exception:
                pass

        if not handler:
            return

        if getattr(elem, 'name', None) and elem.name in ('body', ) and evt in self.window_on_events:
            setattr(self.window, evt, handler)
            return

        if not getattr(elem, '_node', None):
            from thug.DOM.W3C.Core.DOMImplementation import DOMImplementation
            DOMImplementation.createHTMLElement(self.window.doc, elem)

        elem._node._attachEvent(evt, handler, True)

    def set_event_listeners(self, elem):
        p = getattr(elem, '_node', None)

        if p:
            for evt in self.handled_on_events:
                h = getattr(p, evt, None)
                if h:
                    self.attach_event(elem, evt, h)

        listeners = getattr(elem, '_listeners', None)
        if listeners:
            for (eventType, listener, capture) in listeners:
                if eventType in self.handled_events:
                    self.listeners.append((elem, eventType, listener, capture))

    @property
    def javaUserAgent(self):
        javaplugin = log.ThugVulnModules._javaplugin.split('.')
        last = javaplugin.pop()
        version = '%s_%s' % ('.'.join(javaplugin), last)
        return log.ThugOpts.Personality.javaUserAgent % (version, )

    @property
    def javaWebStartUserAgent(self):
        javaplugin = log.ThugVulnModules._javaplugin.split('.')
        last = javaplugin.pop()
        version = '%s_%s' % ('.'.join(javaplugin), last)
        return "JNLP/6.0 javaws/%s (b04) Java/%s" % (version, version, )

    @property
    def shockwaveFlash(self):
        return ','.join(log.ThugVulnModules.shockwave_flash.split('.'))

    def _check_jnlp_param(self, param):
        name  = param.attrs['name']
        value = param.attrs['value']

        if name in ('__applet_ssv_validated', ) and value.lower() in ('true', ):
            log.ThugLogging.log_exploit_event(self.window.url,
                                              'Java WebStart',
                                              'Java Security Warning Bypass (CVE-2013-2423)',
                                              cve = 'CVE-2013-2423')

            log.ThugLogging.log_classifier("exploit", log.ThugLogging.url, "CVE-2013-2423", None)

    def _handle_jnlp(self, data, headers, params):
        try:
            soup = bs4.BeautifulSoup(data, "lxml")
        except Exception: # pragma: no cover
            return

        jnlp = soup.find("jnlp")
        if jnlp is None:
            return

        codebase = jnlp.attrs['codebase'] if 'codebase' in jnlp.attrs else ''

        log.ThugLogging.add_behavior_warn(description = '[JNLP Detected]', method = 'Dynamic Analysis')

        for param in soup.find_all('param'):
            log.ThugLogging.add_behavior_warn(description = '[JNLP] %s' % (param, ), method = 'Dynamic Analysis')
            self._check_jnlp_param(param)

        jars = soup.find_all("jar")
        if not jars:
            return

        headers['User-Agent'] = self.javaWebStartUserAgent

        for jar in jars:
            try:
                url = "%s%s" % (codebase, jar.attrs['href'], )
                self.window._navigator.fetch(url, headers = headers, redirect_type = "JNLP", params = params)
            except Exception:
                pass

    def do_handle_params(self, _object):
        params = dict()

        for child in _object.find_all():
            name = getattr(child, 'name', None)
            if name is None:
                continue

            if name.lower() in ('param', ):
                if all(p in child.attrs for p in ('name', 'value', )):
                    params[child.attrs['name'].lower()] = child.attrs['value']

                    if 'type' in child.attrs:
                        params['type'] = child.attrs['type']

            if name.lower() in ('embed', ):
                self.handle_embed(child)

        if not params:
            return params

        hook = getattr(self, "do_handle_params_hook", None)
        if hook:
            hook(params)

        headers = dict()
        headers['Connection'] = 'keep-alive'

        if 'type' in params:
            headers['Content-Type'] = params['type']
        else:
            name = getattr(_object, 'name', None)

            if name in ('applet', ) or 'archive' in params:
                headers['Content-Type'] = 'application/x-java-archive'

            if 'movie' in params:
                headers['x-flash-version'] = self.shockwaveFlash

        if 'Content-Type' in headers and 'java' in headers['Content-Type'] and log.ThugOpts.Personality.javaUserAgent:
            headers['User-Agent'] = self.javaUserAgent

        for key in ('filename', 'movie', ):
            if key not in params:
                continue

            if log.ThugOpts.features_logging:
                log.ThugLogging.Features.increase_url_count()

            try:
                self.window._navigator.fetch(params[key],
                                             headers = headers,
                                             redirect_type = "params",
                                             params = params)
            except Exception:
                pass

        for key, value in params.items():
            if key in ('filename', 'movie', 'archive', 'code', 'codebase', 'source', ):
                continue

            if key.lower() not in ('jnlp_href', ) and not value.startswith('http'):
                continue

            if log.ThugOpts.features_logging:
                log.ThugLogging.Features.increase_url_count()

            try:
                response = self.window._navigator.fetch(value,
                                                        headers = headers,
                                                        redirect_type = "params",
                                                        params = params)

                if response:
                    self._handle_jnlp(response.content, headers, params)
            except Exception:
                pass

        for p in ('source', 'data', 'archive' ):
            handler = getattr(self, "do_handle_params_{}".format(p), None)
            if handler:
                handler(params, headers)

        return params

    def do_params_fetch(self, url, headers, params):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        try:
            self.window._navigator.fetch(url,
                                         headers = headers,
                                         redirect_type = "params",
                                         params = params)
        except Exception:
            pass

    def do_handle_params_source(self, params, headers):
        if 'source' not in params:
            return

        self.do_params_fetch(params['source'], headers, params)

    def do_handle_params_data(self, params, headers):
        if 'data' not in params:
            return

        self.do_params_fetch(params['data'], headers, params)

    def do_handle_params_archive(self, params, headers):
        if 'archive' not in params:
            return

        if 'codebase' in params:
            archive = urlparse.urljoin(params['codebase'], params['archive'])
        else:
            archive = params['archive']

        self.do_params_fetch(archive, headers, params)

    def handle_object(self, _object):
        log.warning(_object)

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_object_count()

        self.check_small_element(_object, 'object')

        params = self.do_handle_params(_object)

        classid  = _object.get('classid', None)
        _id      = _object.get('id', None)
        codebase = _object.get('codebase', None)
        data     = _object.get('data', None)

        if codebase:
            if log.ThugOpts.features_logging:
                log.ThugLogging.Features.increase_url_count()

            try:
                self.window._navigator.fetch(codebase,
                                             redirect_type = "object codebase",
                                             params = params)
            except Exception: # pragma: no cover
                pass

        if data and not data.startswith('data:'):
            if log.ThugOpts.features_logging:
                log.ThugLogging.Features.increase_url_count()

            try:
                self.window._navigator.fetch(data,
                                             redirect_type = "object data",
                                             params = params)
            except Exception:
                pass

        if not log.ThugOpts.Personality.isIE():
            return

        # if classid and _id:
        if classid:
            try:
                axo = _ActiveXObject(self.window, classid, 'id')
            except TypeError:
                return

            if _id is None:
                return

            try:
                setattr(self.window, _id, axo)
                setattr(self.window.doc, _id, axo)
            except TypeError:
                pass

    def _get_script_for_event_params(self, attr_event):
        params = attr_event.split('(')

        if len(params) > 1:
            params = params[1].split(')')[0]
            return [p for p in params.split(',') if p]

        return list()

    def _handle_script_for_event(self, script):
        attr_for   = script.get("for", None)
        attr_event = script.get("event", None)

        if not attr_for or not attr_event:
            return

        params = self._get_script_for_event_params(attr_event)

        if 'playstatechange' in attr_event.lower() and params:
            with self.context as ctx:
                newState = params.pop()
                ctx.eval("%s = 0;" % (newState.strip(), ))
                try:
                    oldState = params.pop()
                    ctx.eval("%s = 3;" % (oldState.strip(), ))
                except Exception:
                    pass

    def get_script_handler(self, script):
        language = script.get('language', None)
        if language is None:
            language = script.get('type', None)

        if language is None:
            return getattr(self, "handle_javascript")

        try:
            _language = language.lower().split('/')[-1]
            return getattr(self, "handle_{}".format(_language), None)
        except Exception:
            pass

        try:
            _language = language.encode('ascii', 'ignore').lower().split('/')[-1]
            return getattr(self, "handle_{}".format(_language), None)
        except Exception:
            pass

        log.warning("[SCRIPT] Unhandled script type: %s", language)
        return None

    def handle_script(self, script):
        handler = self.get_script_handler(script)
        if not handler:
            return

        node = getattr(script, "_node", None)
        self.window.doc._currentScript = node

        if log.ThugOpts.Personality.isIE():
            self._handle_script_for_event(script)

        handler(script)
        self.handle_events(script._soup)

    def handle_external_javascript_text(self, s, response):
        # First attempt
        # Requests will automatically decode content from the server. Most
        # unicode charsets are seamlessly decoded. When you make a request,
        # Requests makes educated guesses about the encoding of the response
        # based on the HTTP headers.
        try:
            s.text = response.text
            return True
        except Exception:
            pass

        # Last attempt
        # The encoding will be (hopefully) detected through the Encoding class.
        js = response.content
        enc = log.Encoding.detect(js)
        if enc['encoding'] is None:
            return False

        try:
            s.text = js.decode(enc['encoding'])
            return True
        except Exception:
            pass

        log.warning("[handle_external_javascript_text] Encoding failure (URL: %s)", response.url)
        return False

    def handle_external_javascript(self, script):
        src = script.get('src', None)
        if src is None:
            return

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        try:
            response = self.window._navigator.fetch(src, redirect_type = "script src")
        except Exception:
            return

        if response is None or response.status_code in (404, ) or not response.content:
            return

        if log.ThugOpts.code_logging:
            log.ThugLogging.add_code_snippet(response.content, 'Javascript', 'External')

        self.increase_script_chars_count('javascript', 'external', response.text)

        s = self.window.doc.createElement('script')

        for attr in script.attrs:
            if attr.lower() not in ('src', ):
                s.setAttribute(attr, script.get(attr))

        self.handle_external_javascript_text(s, response)

    def increase_javascript_count(self, provenance):
        if not log.ThugOpts.features_logging:
            return

        m = getattr(log.ThugLogging.Features, "increase_{}_javascript_count".format(provenance), None)
        if m:
            m()

    def increase_script_chars_count(self, type_, provenance, code):
        if not log.ThugOpts.features_logging:
            return

        m = getattr(log.ThugLogging.Features, "add_{}_{}_characters_count".format(provenance, type_), None)
        if m:
            m(len(code))

        m = getattr(log.ThugLogging.Features, "add_{}_{}_whitespaces_count".format(provenance, type_), None)
        if m:
            m(len([a for a in code if a.isspace()]))

    def check_strings_in_script(self, code):
        if not log.ThugOpts.features_logging:
            return

        for s in ('iframe', 'embed', 'object', 'frame', 'form'):
            count = code.count(s)

            if not count:
                continue

            m = getattr(log.ThugLogging.Features, "add_{}_string_count".format(s), None)
            if m:
                m(count)

    def get_javascript_provenance(self, script):
        src = script.get('src', None)
        return 'external' if src else 'inline'

    def handle_javascript(self, script):
        log.info(script)

        provenance = self.get_javascript_provenance(script)
        self.handle_external_javascript(script)
        self.increase_javascript_count(provenance)

        js = getattr(script, 'text', None)

        if js:
            if log.ThugOpts.code_logging:
                log.ThugLogging.add_code_snippet(js, 'Javascript', 'Contained_Inside')

            if provenance in ('inline', ):
                self.increase_script_chars_count('javascript', provenance, js)

            self.check_strings_in_script(js)
            self.window.evalScript(js, tag = script)

        self.check_shellcodes()
        self.check_anchors()

    def handle_jscript(self, script):
        self.handle_javascript(script)

    def handle_vbscript(self, script):
        log.info(script)

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_inline_vbscript_count()

        text = script.get_text()
        self.increase_script_chars_count('vbscript', 'inline', text)

        if log.ThugOpts.code_logging:
            log.ThugLogging.add_code_snippet(text, 'VBScript', 'Contained_Inside')

        log.VBSClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url, text)

        try:
            urls = re.findall("(?P<url>https?://[^\s'\"]+)", text)

            for url in urls:
                if log.ThugOpts.features_logging:
                    log.ThugLogging.Features.increase_url_count()

                self.window._navigator.fetch(url, redirect_type = "VBS embedded URL")
        except Exception:
            pass

        log.warning("VBScript parsing not available")

    def handle_vbs(self, script):
        self.handle_vbscript(script)

    def handle_visualbasic(self, script):
        self.handle_vbscript(script)

    def handle_noscript(self, script):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_noscript_count()

    def handle_html(self, html):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_html_count()

    def handle_head(self, head):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_head_count()

    def handle_title(self, title):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_title_count()

    def handle_body(self, body):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_body_count()

    def do_handle_form(self, form):
        from .Window import Window

        log.info(form)

        action = form.get('action', None)
        if action in (None, 'self', ):
            last_url = getattr(log, 'last_url', None)
            action = last_url if last_url else self.window.url

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        _action = log.HTTPSession.normalize_url(self.window, action)
        if _action is None:
            return

        if _action not in self.forms:
            self.forms.append(_action)

        method = form.get('method', 'get')
        payload = None

        for child in form.find_all():
            name = getattr(child, 'name', None)

            if name.lower() in ('input', ):
                if payload is None:
                    payload = dict()

                if all(p in child.attrs for p in ('name', 'value', )):
                    payload[child.attrs['name']] = child.attrs['value']

        headers = dict()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

        try:
            response = self.window._navigator.fetch(action,
                                                    headers = headers,
                                                    method = method.upper(),
                                                    body = payload,
                                                    redirect_type = "form")
        except Exception:
            return

        if response is None or response.status_code in (404, ):
            return

        ctype = response.headers.get('content-type', None)
        if ctype:
            handler = log.MIMEHandler.get_handler(ctype)
            if handler and handler(action, response.content):
                return

        doc    = w3c.parseString(response.content)
        window = Window(_action, doc, personality = log.ThugOpts.useragent)

        dft = DFT(window, forms = self.forms)
        dft.run()

    def handle_param(self, param):
        log.info(param)

    def handle_embed(self, embed):
        log.warning(embed)

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_embed_count()

        src = embed.get('src', None)
        if src is None:
            src = embed.get('data', None)

        if src is None:
            return

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        headers = dict()

        embed_type = embed.get('type', None)
        if embed_type:
            headers['Content-Type'] = embed_type

        if 'Content-Type' in headers:
            if 'java' in headers['Content-Type'] and log.ThugOpts.Personality.javaUserAgent:
                headers['User-Agent'] = self.javaUserAgent

            if 'flash' in headers['Content-Type']:
                headers['x-flash-version']  = self.shockwaveFlash

        try:
            self.window._navigator.fetch(src, headers = headers, redirect_type = "embed")
        except Exception:
            pass

    def handle_applet(self, applet):
        log.warning(applet)

        params = self.do_handle_params(applet)

        archive = applet.get('archive', None)
        if not archive:
            return

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        headers = dict()
        headers['Connection']   = 'keep-alive'
        headers['Content-type'] = 'application/x-java-archive'

        if log.ThugOpts.Personality.javaUserAgent:
            headers['User-Agent'] = self.javaUserAgent

        try:
            self.window._navigator.fetch(archive,
                                         headers = headers,
                                         redirect_type = "applet",
                                         params = params)
        except Exception:
            pass

    def handle_meta(self, meta):
        log.info(meta)

        name = meta.get('name', None)
        if name and name.lower() in ('generator', ):
            content = meta.get('content', None)
            if content:
                log.ThugLogging.add_behavior_warn("[Meta] Generator: %s" % (content, ))

        self.handle_meta_http_equiv(meta)

    def handle_meta_http_equiv(self, meta):
        http_equiv = meta.get('http-equiv', None)
        if http_equiv in (None, 'http-equiv'):
            return

        content = meta.get('content', None)
        if content is None:
            return

        tag = http_equiv.lower().replace('-', '_')
        handler = getattr(self, 'handle_meta_%s' % (tag.encode('ascii', 'ignore'), ), None)
        if handler:
            handler(http_equiv, content)

    def handle_meta_x_ua_compatible(self, http_equiv, content):
        # Internet Explorer < 8.0 doesn't support the X-UA-Compatible header
        # and the webpage doesn't specify a <!DOCTYPE> directive.
        if log.ThugOpts.Personality.isIE() and log.ThugOpts.Personality.browserMajorVersion >= 8:
            if http_equiv.lower() in ('x-ua-compatible', ):
                self.window.doc.compatible = content

    def force_handle_meta_x_ua_compatible(self):
        for meta in self.window.doc.doc.find_all('meta'):
            http_equiv = meta.get('http-equiv', None)
            if http_equiv is None:
                continue

            if not http_equiv.lower() in ('x-ua-compatible', ):
                continue

            content = meta.get('content', None)
            if content is None:
                continue

            self.handle_meta_x_ua_compatible(http_equiv, content)

    def handle_meta_refresh(self, http_equiv, content):
        from .Window import Window

        if http_equiv.lower() != 'refresh':
            return

        if 'url' not in content.lower():
            return

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_meta_refresh_count()
            log.ThugLogging.Features.increase_url_count()

        url = None
        data_uri = True if 'data:' in content else False

        for s in content.split(';'):
            if data_uri is True and url is not None:
                url = "{};{}".format(url, s)

            s = s.strip()
            if s.lower().startswith('url='):
                url = s[4:]

        if not url:
            return

        if url.startswith("'") and url.endswith("'"):
            url = url[1:-1]

        if url in log.ThugLogging.meta and log.ThugLogging.meta[url] >= 3:
            return

        if data_uri:
            self._handle_data_uri(url)
            return

        try:
            response = self.window._navigator.fetch(url, redirect_type = "meta")
        except Exception:
            return

        if response is None or response.status_code in (404, ):
            return

        if url in log.ThugLogging.meta:
            log.ThugLogging.meta[url] += 1
        else:
            log.ThugLogging.meta[url] = 1

        doc    = w3c.parseString(response.content)
        window = Window(self.window.url, doc, personality = log.ThugOpts.useragent)

        dft = DFT(window)
        dft.run()

    def handle_frame(self, frame, redirect_type = 'frame'):
        from .Window import Window

        log.warning(frame)

        src = frame.get('src', None)
        if not src:
            return

        if self._handle_data_uri(src):
            return

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        try:
            response = self.window._navigator.fetch(src, redirect_type = redirect_type)
        except Exception:
            return

        if response is None or response.status_code in (404, ):
            return

        ctype = response.headers.get('content-type', None)
        if ctype:
            handler = log.MIMEHandler.get_handler(ctype)
            if handler and handler(src, response.content):
                return

        _src = log.HTTPSession.normalize_url(self.window, src)
        if _src:
            src = _src

        doc    = w3c.parseString(response.content)
        window = Window(response.url, doc, personality = log.ThugOpts.useragent)

        frame_id = frame.get('id', None)
        if frame_id:
            log.ThugLogging.windows[frame_id] = window

        dft = DFT(window)
        dft.run()

    def handle_iframe(self, iframe):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_iframe_count()

        self.check_small_element(iframe, 'iframe')
        self.handle_frame(iframe, 'iframe')

    def do_handle_font_face_rule(self, rule):
        for p in rule.style:
            if p.name.lower() not in ('src', ):
                continue

            url = p.value
            if url.startswith('url(') and len(url) > 4:
                url = url.split('url(')[1].split(')')[0]

            if log.ThugOpts.features_logging:
                log.ThugLogging.Features.increase_url_count()

            if self._handle_data_uri(url):
                continue

            try:
                self.window._navigator.fetch(url, redirect_type = "font face")
            except Exception:
                return

    def handle_style(self, style):
        log.info(style)

        cssparser = CSSParser(loglevel = logging.CRITICAL, validate = False)

        try:
            sheet = cssparser.parseString(style.text)
        except Exception:
            return

        for rule in sheet:
            if rule.type == rule.FONT_FACE_RULE:
                self.do_handle_font_face_rule(rule)

    def _handle_data_uri(self, uri):
        """
        Data URI Scheme
        data:[<MIME-type>][;charset=<encoding>][;base64],<data>

        The encoding is indicated by ;base64. If it is present the data is
        encoded as base64. Without it the data (as a sequence of octets) is
        represented using ASCII encoding for octets inside the range of safe
        URL characters and using the standard %xx hex encoding of URLs for
        octets outside that range. If <MIME-type> is omitted, it defaults to
        text/plain;charset=US-ASCII. (As a shorthand, the type can be omitted
        but the charset parameter supplied.)

        Some browsers (Chrome, Opera, Safari, Firefox) accept a non-standard
        ordering if both ;base64 and ;charset are supplied, while Internet
        Explorer requires that the charset's specification must precede the
        base64 token.
        """
        if not uri.lower().startswith("data:"):
            return False

        log.URLClassifier.classify(uri)

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_data_uri_count()

        h = uri.split(",")
        if len(h) < 2 or not h[1]:
            return False

        data = h[1]
        opts = h[0][len("data:"):].split(";")

        if 'base64' in opts:
            try:
                data = base64.b64decode(h[1])
            except TypeError:
                try:
                    data = base64.b64decode(urlparse.unquote(h[1]))
                except Exception:
                    log.warning("[WARNING] Error while handling data URI: %s", data)
                    return False

            opts.remove('base64')

        if not opts or not opts[0]:
            opts = ["text/plain", "charset=US-ASCII"]

        mimetype = opts[0]

        if mimetype in ('text/html', ):
            from .Window import Window

            doc    = w3c.parseString(data)
            window = Window(self.window.url, doc, personality = log.ThugOpts.useragent)

            dft = DFT(window)
            dft.run()
            return True

        handler = log.MIMEHandler.get_handler(mimetype)
        if handler:
            handler(self.window.url, data)
            return True

        return False

    def handle_a(self, anchor):
        log.info(anchor)

        if log.ThugOpts.extensive:
            log.info(anchor)

            href = anchor.get('href', None)
            if not href:
                return

            if self._handle_data_uri(href):
                return

            try:
                response = self.window._navigator.fetch(href, redirect_type = "anchor")
            except Exception:
                return

            if response is None or response.status_code in (404, ):
                return

        self.anchors.append(anchor)

    def handle_link(self, link):
        log.info(link)

        href = link.get('href', None)
        if not href:
            return

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_url_count()

        if self._handle_data_uri(href):
            return

        try:
            response = self.window._navigator.fetch(href, redirect_type = "link")
        except Exception:
            return

        if response is None or response.status_code in (404, ):
            return

    def check_anchors(self):
        clicked_anchors = [a for a in self.anchors if '_clicked' in a.attrs]
        if not clicked_anchors:
            return

        clicked_anchors.sort(key = lambda anchor: anchor['_clicked'])

        for anchor in clicked_anchors:
            del anchor['_clicked']

            if 'href' not in anchor:
                continue

            href = anchor['href']

            if 'target' in anchor.attrs and not anchor.attrs['target'] in ('_self', ):
                pid = os.fork()
                if pid == 0:
                    self.follow_href(href)
                else:
                    os.waitpid(pid, 0)
            else:
                self.follow_href(href)

    def follow_href(self, href):
        from .Window import Window

        doc    = w3c.parseString('')
        window = Window(self.window.url, doc, personality = log.ThugOpts.useragent)
        window = window.open(href)

        if window:
            dft = DFT(window)
            dft.run()

    def do_handle(self, child, soup, skip = True):
        name = getattr(child, "name", None)

        if name is None:
            return False

        if skip and name in ('object', 'applet', ):
            return False

        # FIXME: this workaround should be not necessary once the Python 3
        # porting will be completed.
        handler = None

        try:
            handler = getattr(self, "handle_%s" % (str(name.lower()), ), None)
        except Exception:
            try:
                handler = getattr(self, "handle_%s" % (name.encode('utf-8', 'replace'), ), None)
            except Exception:
                pass

        child._soup = soup

        if handler:
            handler(child)
            if name in ('script', ):
                self.run_htmlclassifier(soup)
            return True

        return False

    def check_hidden_element(self, element):
        if not log.ThugOpts.features_logging:
            return

        attrs = getattr(element, 'attrs', None)
        if attrs is None:
            return

        if 'hidden' in attrs:
            log.ThugLogging.Features.increase_hidden_count()

    def check_small_element(self, element, tagname):
        if not log.ThugOpts.features_logging:
            return

        attrs = getattr(element, 'attrs', None)
        if attrs is None:
            return None

        attrs_count = 0
        element_area = 1

        for key in ('width', 'height'):
            if key not in attrs:
                continue

            try:
                value = int(attrs[key].split('px')[0])
            except Exception:
                continue

            if value <= 2:
                m = getattr(log.ThugLogging.Features, 'increase_{}_small_{}_count'.format(tagname, key), None)
                if m:
                    m()

            attrs_count += 1
            element_area *= value

        if attrs_count > 1 and element_area < 30:
            m = getattr(log.ThugLogging.Features, 'increase_{}_small_area_count'.format(tagname), None)
            if m:
                m()

    def run_htmlclassifier(self, soup):
        try:
            log.HTMLClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else self.window.url, str(soup))
        except Exception:
            pass

    def _run(self, soup = None):
        if soup is None:
            soup = self.window.doc.doc

        _soup = soup

        # Dirty hack
        for p in soup.find_all('object'):
            self.check_hidden_element(p)
            self.handle_object(p)
            self.run_htmlclassifier(soup)

        for p in soup.find_all('applet'):
            self.check_hidden_element(p)
            self.handle_applet(p)

        for child in soup.descendants:
            if child is None:
                continue

            self.check_hidden_element(child)

            parents = [p.name.lower() for p in child.parents]
            if 'noscript' in parents:
                continue

            self.set_event_handler_attributes(child)
            if not self.do_handle(child, soup):
                continue

            analyzed = set()
            recur    = True

            while recur:
                recur = False

                try:
                    if tuple(soup.descendants) == tuple(_soup.descendants):
                        break

                    for _child in set(soup.descendants) - set(_soup.descendants):
                        if _child not in analyzed:
                            analyzed.add(_child)
                            recur = True

                            name = getattr(_child, "name", None)
                            if name:
                                self.do_handle(_child, soup, False)
                except AttributeError:
                    break

            analyzed.clear()
            _soup = soup

        self.window.doc._readyState = "complete"

        for child in soup.descendants:
            self.set_event_listeners(child)

        self.handle_events(soup)

    def handle_events(self, soup):
        for evt in self.handled_on_events:
            try:
                self.handle_window_event(evt)
                self.run_htmlclassifier(soup)
            except Exception:
                log.warning("[handle_window_event] Event %s not properly handled", evt)

        for evt in self.handled_on_events:
            try:
                self.handle_document_event(evt)
                self.run_htmlclassifier(soup)
            except Exception:
                log.warning("[handle_document_event] Event %s not properly handled", evt)

        for evt in self.handled_events:
            try:
                self.handle_element_event(evt)
                self.run_htmlclassifier(soup)
            except Exception:
                log.warning("[handle_element_event] Event %s not properly handled", evt)

    def run(self):
        with self.context as ctx:  # pylint:disable=unused-variable
            self._run()
            self.check_shellcodes()
