#!/usr/bin/env python
#
# Window.py
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

import sched
import time
import logging
import traceback
import base64
import numbers
import collections
import datetime
# import types
import random
import six
import bs4
import six.moves.urllib_parse as urllib

from thug.ActiveX.ActiveX import _ActiveXObject
# from thug.AST.AST import AST
# from thug.Debugger import Shellcode
from thug.Java.java import java

from thug.DOM.W3C import w3c
from .JSClass import JSClass
from .JSClass import JSClassConstructor
from .JSClass import JSClassPrototype
from .JSEngine import JSEngine
from .JSInspector import JSInspector
from .Navigator import Navigator
from .Location import Location
from .Screen import Screen
from .History import History
from .CCInterpreter import CCInterpreter
from .LocalStorage import LocalStorage
from .SessionStorage import SessionStorage
from .w3c_bindings import w3c_bindings

sched = sched.scheduler(time.time, time.sleep)
log = logging.getLogger("Thug")


class Window(JSClass):
    class Timer(object):
        def __init__(self, window, code, delay, repeat, lang = 'JavaScript'):
            self.window  = window
            self.code    = code
            self.delay   = float(delay) / 1000
            self.repeat  = repeat
            self.lang    = lang
            self.running = True

        def start(self):
            self.event = sched.enter(self.delay, 1, self.execute, ())
            try:
                sched.run()
            except Exception as e:
                log.warning("[Timer] Scheduler error: %s", str(e))

        def stop(self):
            self.running = False
            if self.event in sched.queue:
                sched.cancel(self.event)

        def execute(self):
            if not self.running:
                return None

            with self.window.context as ctx:
                try:
                    if isinstance(self.code, six.string_types):
                        return ctx.eval(self.code)

                    if log.JSEngine.isJSFunction(self.code):
                        return self.code()

                    log.warning("Error while handling timer callback")

                    if log.ThugOpts.Personality.isIE():
                        raise TypeError()

                    return None
                except Exception:
                    if log.ThugOpts.Personality.isIE():
                        raise TypeError()

                    return None

            if self.repeat:
                self.start()

    def __init__(self, url, dom_or_doc, navigator = None, personality = 'winxpie60', name="",
                 target='_blank', parent = None, opener = None, replace = False, screen = None,
                 width = 800, height = 600, left = 0, top = None, **kwds):

        self.url = url
        self.doc = w3c.getDOMImplementation(dom_or_doc, **kwds) if isinstance(dom_or_doc, bs4.BeautifulSoup) else dom_or_doc

        self.doc.window        = self
        self.doc.contentWindow = self

        for p in w3c_bindings:
            setattr(self, p, w3c_bindings[p])

        self._navigator = navigator if navigator else Navigator(personality, self)
        self._location  = Location(self)
        self._history   = parent.history if parent and parent.history else History(self)

        if url not in ('about:blank', ):
            self._history.update(url, replace)

        self.doc.location = property(self.getLocation, self.setLocation)

        self._target = target
        self._parent = parent if parent else self
        self._opener = opener
        self._screen = screen or Screen(width, height, 32)
        self._closed = False

        self._personality = personality
        self.__init_personality()

        self.name          = name
        self.defaultStatus = ""
        self.status        = ""
        self._left         = left
        self._top          = top if top else self
        self._screen_top   = random.randint(0, 30)
        self.innerWidth    = width
        self.innerHeight   = height
        self.outerWidth    = width
        self.outerHeight   = height
        self.timers        = []
        self.java          = java()

        self._symbols      = set()
        self._methods      = tuple()

        log.MIMEHandler.window = self

    def __getattr__(self, key):
        if key in self._symbols:
            raise AttributeError(key)

        if key in ('__members__', '__methods__'):
            raise AttributeError(key)

        if key == 'constructor':
            return JSClassConstructor(self.__class__)

        if key == 'prototype':
            return JSClassPrototype(self.__class__)

        prop = self.__dict__.setdefault('__properties__', {}).get(key, None)

        if prop and isinstance(prop[0], collections.Callable):
            return prop[0]()

        if log.ThugOpts.Personality.isIE() and key.lower() in ('wscript', 'wsh', ):
            return self.WScript

        if log.ThugOpts.Personality.isIE():
            if key in self.WScript.__dict__ and callable(self.WScript.__dict__[key]):
                return self.WScript.__dict__[key]

        context = self.__class__.__dict__['context'].__get__(self, Window)

        try:
            self._symbols.add(key)
            symbol = context.eval(key)
        except Exception:
            raise AttributeError(key)
        finally:
            self._symbols.discard(key)

        if log.JSEngine.isJSFunction(symbol):
            _method = None

            if symbol in self._methods:
                _method = symbol.clone()

            if _method is None:
                # _method = types.MethodType(symbol, Window)
                _method = six.create_bound_method(symbol, Window)

            setattr(self, key, _method)
            context.locals[key] = _method
            return _method

        if isinstance(symbol, (six.string_types,
                               bool,
                               numbers.Number,
                               datetime.datetime)):
            setattr(self, key, symbol)
            context.locals[key] = symbol
            return symbol

        if log.JSEngine.isJSObject(symbol):
            setattr(self, key, symbol)
            context.locals[key] = symbol
            return symbol

        raise AttributeError(key)

    @property
    def closed(self):
        return self._closed

    def close(self):
        self._closed = True

    @property
    def this(self):
        return self

    @property
    def window(self):
        return self

    @property
    def self(self):
        return self

    def get_top(self):
        return self._top

    def set_top(self, top):
        self._top = top

    top = property(get_top, set_top)

    @property
    def _document(self):
        return self.doc

    def _findAll(self, tags):
        return self.doc.doc.find_all(tags, recursive = True)

    @property
    def frames(self):
        """an array of all the frames (including iframes) in the current window"""
        from thug.DOM.W3C.HTML.HTMLCollection import HTMLCollection

        frames = set()
        for frame in self._findAll(['frame', 'iframe']):
            if not getattr(frame, '_node', None):
                from thug.DOM.W3C.Core.DOMImplementation import DOMImplementation
                DOMImplementation.createHTMLElement(self.window.doc, frame)

            frames.add(frame._node)

        return HTMLCollection(self.doc, list(frames))

    @property
    def length(self):
        """the number of frames (including iframes) in a window"""
        return len(self._findAll(['frame', 'iframe']))

    @property
    def history(self):
        """the History object for the window"""
        return self._history

    def getLocation(self):
        """the Location object for the window"""
        return self._location

    def setLocation(self, location):
        self._location.href = location

    location = property(getLocation, setLocation)

    @property
    def navigator(self):
        """the Navigator object for the window"""
        return self._navigator

    @property
    def opener(self):
        """a reference to the window that created the window"""
        return self._opener

    @property
    def pageXOffset(self):
        return 0

    @property
    def pageYOffset(self):
        return 0

    @property
    def parent(self):
        return self._parent

    @property
    def screen(self):
        return self._screen

    @property
    def screenLeft(self):
        return self._left

    @property
    def screenTop(self):
        return self._screen_top

    @property
    def screenX(self):
        return self._left

    @property
    def screenY(self):
        return self._screen_top

    def _do_ActiveXObject(self, cls, typename = 'name'):
        return _ActiveXObject(self, cls, typename)

    def alert(self, text):
        """
        Display an alert dialog with the specified text.
        Syntax

        window.alert(text)

        Parameters

        text is a string of the text you want displayed in the alert dialog.
        """
        log.TextClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url_fetched, str(text))

        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_alert_count()

        log.warning('[Window] Alert Text: %s', str(text))

    def back(self):
        """
        Returns the window to the previous item in the history.
        Syntax

        window.back()

        Parameters

        None.
        """
        pass

    def blur(self):
        """
        Shifts focus away from the window.
        Syntax

        window.blur()

        Parameters

        None.
        """
        pass

    def captureEvents(self, eventType):
        """
        Registers the window to capture all events of the specified type.
        Syntax

        window.captureEvents(Event.eventType)

        Parameters

        eventType is a string
        """
        self.alert("[Captured Event] %s" % (eventType, ))

    def clearInterval(self, intervalID):
        """
        Clears a delay that's been set for a specific function.
        Syntax

        window.clearInterval(intervalID)

        Parameters

        intervalID is the ID of the specific interval you want to clear.
        """
        self.timers[intervalID].stop()

    def clearTimeout(self, timeoutID):
        """
        Clears the delay set by window.setTimeout().
        Syntax

        window.clearTimeout(timeoutID)

        Parameters

        timeoutID is the ID of the timeout you wish you clear.
        """
        self.timers[timeoutID].stop()

    def confirm(self, text):
        """
        Displays a dialog with a message that the user needs to respond to.
        Syntax

        result = window.confirm(text)

        Parameters

        text is a string.

        result is a boolean value indicating whether OK or Cancel was selected.
        """
        log.TextClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url_fetched, str(text))
        return True

    def dump(self, text):
        """
        Prints messages to the console.
        Syntax

        window.dump(text)

        Parameters

        text is a string.
        """
        log.TextClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url_fetched, str(text))
        self.alert(text)

    def focus(self):
        """
        Sets focus on the window.
        Syntax

        window.focus()

        Parameters

        None.
        """
        pass

    def forward(self):
        """
        Moves the window one document forward in the history.
        Syntax

        window.forward()

        Parameters

        None.
        """
        self._history.forward()

    def GetAttention(self):
        """
        Flashes the application icon to get the user's attention.
        Syntax

        window.GetAttention()

        Parameters

        None.
        """
        pass

    def getSelection(self):
        """
        Returns the selection (generally text).
        Syntax

        selection = window.getSelection()

        Parameters

        selection is a selection object.
        """
        return None

    def home(self):
        """
        Returns the window to the home page.
        Syntax

        window.home()

        Parameters

        None.
        """
        self.open()

    def moveBy(self, deltaX, deltaY):
        """
        Moves the current window by a specified amount.
        Syntax

        window.moveBy(deltaX, deltaY)

        Parameters

        deltaX is the amount of pixels to move the window horizontally.
        deltaY is the amount of pixels to move the window vertically.
        """
        pass

    def moveTo(self, x, y):
        """
        Moves the window to the specified coordinates.
        Syntax

        window.moveTo(x, y)

        Parameters

        x is the horizontal coordinate to be moved to.
        y is the vertical coordinate to be moved to.
        """
        pass

    def prompt(self, text, defaultText = None):
        """
        Returns the text entered by the user in a prompt dialog.
        """
        log.TextClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url_fetched, str(text))
        return defaultText if defaultText else ""

    def releaseEvents(self, eventType):
        """
        Releases the window from trapping events of a specific type.
        Syntax

        window.releaseEvents(Event.eventType)

        Parameters

        eventType is a string
        """
        self.alert("[Released Event] %s" % (eventType, ))

    def resizeBy(self, xDelta, yDelta):
        """
        Resizes the current window by a certain amount.
        Syntax

        window.resizeBy(xDelta, yDelta)

        Parameters

        xDelta is the number of pixels to grow the window horizontally.
        yDelta is the number of pixels to grow the window vertically.
        """
        pass

    def resizeTo(self, iWidth, iHeight):
        """
        Dynamically resizes window.
        Syntax

        window.resizeTo(iWidth, iHeight)

        Parameters

        iWidth is an integer representing the new width in pixels.
        iHeight is an integer value representing the new height in pixels.
        """
        pass

    def scroll(self, x, y):
        """
        Scrolls the window to a particular place in the document.
        Syntax

        window.scroll(x-coord, y-coord)

        Parameters

        x-coord is the pixel along the horizontal axis of the document that
        you want displayed in the upper left.
        y-coord is the pixel along the vertical axis of the document that you
        want displayed in the upper left.
        """
        pass

    def scrollBy(self, xDelta, yDelta):
        """
        Scrolls the document in the window by the given amount.
        Syntax

        window.scrollBy(xDelta, yDelta)

        Parameters

        xDelta is the amount of pixels to scroll horizontally.

        yDelta is the amount of pixels to scroll vertically.
        """
        pass

    def scrollByLines(self, lines):
        """
        Scrolls the document by the given number of lines.
        Syntax

        window.scrollByLines(lines)

        Parameters

        lines is the number of lines.
        """
        pass

    def scrollByPages(self, pages):
        """
        Scrolls the current document by the specified number of pages.
        Syntax

        window.scrollByPages(pages)

        Parameters

        pages is the number of pages to scroll.
        """
        pass

    def scrollTo(self, x, y):
        """
        Scrolls to a particular set of coordinates in the document.
        Syntax

        window.scrollTo(x-coord, y-coord)

        Parameters

        x-coord is the pixel along the horizontal axis of the document that you
        want displayed in the upper left.

        y-coord is the pixel along the vertical axis of the document that you
        want displayed in the upper left.
        """
        pass

    def setInterval(self, f, delay, lang = 'JavaScript'):
        """
        Set a delay for a specific function.
        Syntax

        ID = window.setInterval("funcName", delay)

        Parameters

        funcName is the name of the function for which you want to set a
        delay.

        delay is the number of milliseconds (thousandths of a second)
        that the function should be delayed.

        ID is the interval ID.
        """
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_setinterval_count()

        if log.ThugOpts.Personality.isIE() and not f:
            raise TypeError()

        if log.ThugOpts.delay:
            delay = min(delay, log.ThugOpts.delay)

        timer = Window.Timer(self, f, delay, True, lang)
        self.timers.append(timer)
        timer.start()

        return len(self.timers) - 1

    def setTimeout(self, f, delay = 0, lang = 'JavaScript'):
        """
        Sets a delay for executing a function.
        Syntax

        ID = window.setTimeout("funcName", delay)

        Parameters

        funcName is the name of the function for which you want to set a
        delay.

        delay is the number of milliseconds (thousandths of a second)
        that the function should be delayed.

        ID is the interval ID.
        """
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_settimeout_count()

        if log.ThugOpts.Personality.isIE() and not f:
            raise TypeError()

        if log.ThugOpts.delay:
            delay = min(delay, log.ThugOpts.delay)

        timer = Window.Timer(self, f, delay, False, lang)
        self.timers.append(timer)
        timer.start()

        return len(self.timers) - 1

    def stop(self):
        """
        This method stops window loading.
        Syntax

        window.stop()

        Parameters

        None.
        """
        pass

    def _attachEvent(self, sEvent, fpNotify, useCapture = False):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_attachevent_count()

        setattr(self, sEvent.lower(), fpNotify)

    def _detachEvent(self, sEvent, fpNotify):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_detachevent_count()

        notify = getattr(self, sEvent.lower(), None)
        if notify is None:
            return

        if notify in (fpNotify, ):
            delattr(self, sEvent.lower())

    def _addEventListener(self, _type, listener, useCapture = False):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_addeventlistener_count()

        setattr(self, 'on%s' % (_type.lower(), ), listener)

    def _removeEventListener(self, _type, listener, useCapture = False):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_removeeventlistener_count()

        _listener = getattr(self, 'on%s' % (_type.lower(), ), None)
        if _listener is None:
            return

        if _listener in (listener, ):
            delattr(self, 'on%s' % (_type.lower(), ))

    def _CollectGarbage(self):
        pass

    def _navigate(self, location):
        self.location = location
        return 0

    def _execScript(self, code, language = "JScript"):
        if log.ThugOpts.code_logging:
            log.ThugLogging.add_code_snippet(code, language, 'Contained_Inside')

        if language.lower().startswith(('jscript', 'javascript')):
            self.eval(code)

        if language.lower().startswith('vbs'):
            log.VBSClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url, code)

        return None

    def __init_personality(self):
        if log.ThugOpts.Personality.isIE():
            self.__init_personality_IE()
            return

        if log.ThugOpts.Personality.isFirefox():
            self.__init_personality_Firefox()
            return

        if log.ThugOpts.Personality.isChrome():
            self.__init_personality_Chrome()
            return

        if log.ThugOpts.Personality.isSafari():
            self.__init_personality_Safari()
            return

    def __init_personality_IE(self):
        from .ClipboardData import ClipboardData
        from .Console import Console
        from .External import External
        from thug.DOM.W3C.DOMParser import DOMParser

        log.ThugOpts.activex_ready = False

        if not (log.ThugOpts.local and log.ThugOpts.attachment):
            self.XMLHttpRequest = self._XMLHttpRequest

        self.document                 = self._document
        self.ActiveXObject            = self._do_ActiveXObject
        self.DeferredListDataComplete = self._DeferredListDataComplete
        self.CollectGarbage           = self._CollectGarbage
        self.WScript                  = _ActiveXObject(self, "WScript.Shell")
        self.navigate                 = self._navigate
        self.clientInformation        = self.navigator
        self.clipboardData            = ClipboardData()
        self.external                 = External()
        self.console                  = Console()
        self.ScriptEngineMajorVersion = log.ThugOpts.Personality.ScriptEngineMajorVersion
        self.ScriptEngineMinorVersion = log.ThugOpts.Personality.ScriptEngineMinorVersion
        self.ScriptEngineBuildVersion = log.ThugOpts.Personality.ScriptEngineBuildVersion

        if log.ThugOpts.Personality.browserMajorVersion < 11:
            self.execScript = self._execScript
            self.attachEvent = self._attachEvent
            self.detachEvent = self._detachEvent

        if log.ThugOpts.Personality.browserMajorVersion >= 8:
            self.DOMParser           = DOMParser
            self.addEventListener    = self._addEventListener
            self.removeEventListener = self._removeEventListener
            self.localStorage        = LocalStorage()
            self.sessionStorage      = SessionStorage()

        self.doc.parentWindow = self._parent

        log.ThugOpts.activex_ready = True

    def __init_personality_Firefox(self):
        from .Components import Components
        from .Console import Console
        from .Crypto import Crypto
        from .Map import Map
        from .MozConnection import mozConnection
        from .Sidebar import Sidebar
        from thug.DOM.W3C.DOMParser import DOMParser

        self.document            = self._document
        self.DOMParser           = DOMParser
        self.XMLHttpRequest      = self._XMLHttpRequest
        self.addEventListener    = self._addEventListener
        self.removeEventListener = self._removeEventListener
        self.crypto              = Crypto()
        self.sidebar             = Sidebar()
        self.Components          = Components()
        self.console             = Console()
        self.localStorage        = LocalStorage()
        self.sessionStorage      = SessionStorage()

        if log.ThugOpts.Personality.browserMajorVersion > 32:
            self.RadioNodeList = None

        if log.ThugOpts.Personality.browserMajorVersion > 12:
            self.Map = Map()

        if log.ThugOpts.Personality.browserMajorVersion > 11:
            self.navigator.mozConnection = mozConnection()

        with self.context as ctxt:
            if log.ThugOpts.Personality.browserMajorVersion <= 20:
                ctxt.eval("delete Math.imul;")
            if log.ThugOpts.Personality.browserMajorVersion <= 4:
                ctxt.eval("delete Array.isArray;")

    def __init_personality_Chrome(self):
        from .Chrome import Chrome
        from .Console import Console
        from .External import External
        from thug.DOM.W3C.DOMParser import DOMParser

        self.document            = self._document
        self.DOMParser           = DOMParser
        self.XMLHttpRequest      = self._XMLHttpRequest
        self.addEventListener    = self._addEventListener
        self.removeEventListener = self._removeEventListener
        self.clientInformation   = self.navigator
        self.external            = External()
        self.chrome              = Chrome()
        self.console             = Console()
        self.localStorage        = LocalStorage()
        self.sessionStorage      = SessionStorage()
        self.onmousewheel        = None

    def __init_personality_Safari(self):
        from .Console import Console
        from thug.DOM.W3C.DOMParser import DOMParser

        self.document            = self._document
        self.DOMParser           = DOMParser
        self.XMLHttpRequest      = self._XMLHttpRequest
        self.addEventListener    = self._addEventListener
        self.removeEventListener = self._removeEventListener
        self.clientInformation   = self.navigator
        self.console             = Console()
        self.localStorage        = LocalStorage()
        self.sessionStorage      = SessionStorage()
        self.onmousewheel        = None

    def eval(self, script):
        if not script: # pragma: no cover
            return None

        log.ThugLogging.add_code_snippet(script,
                                         language = 'Javascript',
                                         relationship = 'eval argument',
                                         check = True)

        return self.evalScript(script)

    @property
    def context(self):
        # if not hasattr(self, '_context'):
        if '_context' not in self.__dict__:
            log.JSEngine = JSEngine(self)
            self._context = log.JSEngine.context

        return self._context

    def evalScript(self, script, tag = None):
        if log.ThugOpts.verbose or log.ThugOpts.debug:
            log.info(script)

        result = 0

        try:
            log.JSClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else log.last_url, script)

            if log.ThugOpts.code_logging:
                log.ThugLogging.add_code_snippet(script, 'Javascript', 'Contained_Inside')
        except Exception as e:
            log.warning("[Window] JSClassifier error: %s", str(e))

        if tag:
            self.doc.current = tag
        else:
            try:
                body = self.doc.body
            except Exception:
                # This code is for when you are desperate :)
                body = self.doc.getElementsByTagName('body')[0]

            if body and body.tag.contents:
                self.doc.current = body.tag.contents[-1]
            else:
                self.doc.current = self.doc.doc.contents[-1]

        with self.context as ctxt:
            # try:
            #    ast = AST(script, self)
            #    ast.walk()
            # except Exception:
            #    log.warning(traceback.format_exc())
            #    return result

            if log.ThugOpts.Personality.isIE():
                cc = CCInterpreter()
                script = cc.run(script)

            # shellcode = Shellcode.Shellcode(self, ctxt, ast, script)
            # result    = shellcode.run()
            inspector = JSInspector(self, ctxt, script)
            result = inspector.run()

        log.ThugLogging.ContextAnalyzer.analyze(self)
        return result

    def unescape(self, s):
        i  = 0
        sc = list()

        if len(s) > 16:
            log.ThugLogging.shellcodes.add(s)

        # %xx format
        if '%' in s and '%u' not in s:
            return urllib.unquote(s)

        # %uxxxx format
        while i < len(s):
            if s[i] == '"':
                i += 1
                continue

            if s[i] == '%' and (i + 1) < len(s) and s[i + 1] == 'u':
                if (i + 6) <= len(s):
                    currchar = int(s[i + 2: i + 4], 16)
                    nextchar = int(s[i + 4: i + 6], 16)
                    sc.append(chr(nextchar))
                    sc.append(chr(currchar))
                    i += 6
                elif (i + 3) <= len(s):
                    currchar = int(s[i + 2: i + 4], 16)
                    sc.append(chr(currchar))
                    i += 3
            else:
                sc.append(s[i])
                i += 1

        return ''.join(sc)

    def atob(self, s):
        """
        The atob method decodes a base-64 encoded string
        """
        return base64.b64decode(s)

    def btoa(self, s):
        """
        The btoa method encodes a string in base-64
        """
        return base64.b64encode(s)

    def decodeURIComponent(self, s):
        return urllib.unquote(s) if s else ""

    def Image(self, width = 800, height = 600):
        return self.doc.createElement('img')

    def _XMLHttpRequest(self):
        return _ActiveXObject(self, 'microsoft.xmlhttp')

    def _DeferredListDataComplete(self): # pragma: no cover
        for name in self.context.locals.keys():
            local = getattr(self.context.locals, name, None)
            if not local:
                continue

            rootFolder = getattr(local, 'rootFolder', None)
            if not rootFolder:
                continue

            try:
                self._navigator.fetch(rootFolder, redirect_type = "Sharepoint")
            except Exception:
                log.warning(traceback.format_exc())

    def getComputedStyle(self, element, pseudoelt = None):
        if log.ThugOpts.features_logging:
            log.ThugLogging.Features.increase_getcomputedstyle_count()

        return getattr(element, 'style', None)

    def open(self, url = None, name = '_blank', specs = '', replace = False):
        if url and url not in ('about:blank', ):
            if self.url not in ('about:blank', ):
                log.last_url = url

            try:
                response = self._navigator.fetch(url, redirect_type = "window open")
            except Exception:
                return None

            if response is None or not response.ok:
                return None

            html = response.content

            if response.history:
                url = response.url

            try:
                log.HTMLClassifier.classify(log.ThugLogging.url if log.ThugOpts.local else url, html)
            except Exception as e:
                log.warning("[Window] HTMLClassifier error: %s", str(e))

            content_type = response.headers.get('content-type' , None)
            if content_type:
                handler = log.MIMEHandler.get_handler(content_type)

                # No need to invoke the MIME handler here because Navigator
                # fetch method has already taken care of it. Here we have
                # just to check if a MIME handler exists and stop further
                # processing if it does.
                if handler:
                    return None

            # Log response here
            kwds = {'referer' : self.url}
            if 'set-cookie' in response.headers:
                kwds['cookie'] = response.headers['set-cookie']
            if 'last-modified' in response.headers:
                kwds['lastModified'] = response.headers['last-modified']
        else:
            url  = 'about:blank'
            html = ''
            kwds = {}

        dom = bs4.BeautifulSoup(html, "html5lib")

        for spec in specs.split(','):
            spec = [s.strip() for s in spec.split('=')]

            if len(spec) == 2:
                if spec[0] in ['width', 'height', 'left', 'top']:
                    kwds[spec[0]] = int(spec[1])

        if name in ['_blank', '_parent', '_self', '_top']:
            kwds['target'] = name
            name = ''
        else:
            kwds['target'] = '_blank'

        return Window(url, dom, navigator = None, personality = self._personality,
                        name = name, parent = self, opener = self, replace = replace, **kwds)
