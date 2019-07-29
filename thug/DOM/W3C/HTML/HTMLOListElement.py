#!/usr/bin/env python

from .HTMLElement import HTMLElement
from .attr_property import attr_property


class HTMLOListElement(HTMLElement):
    compact = attr_property("compact", bool)
    start   = attr_property("start", int)
    type    = attr_property("type")

    def __init__(self, doc, tag):
        HTMLElement.__init__(self, doc, tag)
