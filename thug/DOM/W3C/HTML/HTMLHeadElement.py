#!/usr/bin/env python

from .HTMLElement import HTMLElement
from .attr_property import attr_property


class HTMLHeadElement(HTMLElement):
    profile = attr_property("profile")

    def __init__(self, doc, tag):
        HTMLElement.__init__(self, doc, tag)
