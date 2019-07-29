#!/usr/bin/env python

from .HTMLElement import HTMLElement
from .attr_property import attr_property


class HTMLFrameSetElement(HTMLElement):
    cols = attr_property("cols")
    rows = attr_property("rows")

    def __init__(self, doc, tag):
        HTMLElement.__init__(self, doc, tag)
