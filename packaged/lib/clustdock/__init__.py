# -*- coding: utf-8 -*-
'''
@author Antoine Sax <antoine.sax@atos.net>
@copyright 2015  Bull S.A.S.  -  All rights reserved.\n
           This is not Free or Open Source software.\n
           Please contact Bull SAS for details about its license.\n
           Bull - Rue Jean Jaurès - B.P. 68 - 78340 Les Clayes-sous-Bois
@file clustdock/__init__.py
@namespace clustdock Clustdock Module
'''
import re
import logging

DOCKER_NODE = "docker"
LIBVIRT_NODE = "libvirt"

_LOGGER = logging.getLogger(__name__)


class VirtualNode(object):
    '''Represents a virtual node'''

    def __init__(self, name, host=None, ip=None, **kwargs):
        self.name = name
        self.ip = ip if ip is not None else ''
        if host:
            self.host = host
        else:
            self.host = 'localhost'
        self.clustername, self.idx = VirtualNode.split_name(self.name)
        self.unreachable = False

    @classmethod
    def split_name(cls, nodename):
        try:
            res = re.search(r'([a-z-_]+)(\d+)', nodename).groups()
            clustername = res[0]
            idx = int(res[1])
            return (clustername, idx)
        except AttributeError:
            _LOGGER.error("Error when splitting %s: doesn't match regex", nodename)
            return (nodename, 0)

    def start(self):
        """Start virtual node"""
        raise NotImplementedError("Must be redefine is subclasses")

    def stop(self):
        """Stop virtual node"""
        raise NotImplementedError("Must be redefine is subclasses")

    def get_ip(self):
        """Get ip of the node"""
        raise NotImplementedError("Must be redefine is subclasses")

    def is_alive(self):
        """Return True if node is still defined, else False"""
        raise NotImplementedError("Must be redefine is subclasses")


def format_dict(dico, **kwargs):
    new = {}
    for key, value in dico.items():
        if isinstance(value, dict):
            new[key] = format_dict(value, **kwargs)
        elif isinstance(value, str):
            new[key] = value.format(**kwargs)
        elif isinstance(value, tuple):
            new[key] = format_list(value, **kwargs)
        elif isinstance(value, list):
            new[key] = format_list(value, **kwargs)
        else:
            new[key] = value
    return new


def format_list(liste, **kwargs):
    new = []
    for item in liste:
        if isinstance(item, str):
            new.append(item.format(**kwargs))
        elif isinstance(item, tuple):
            new.append(format_list(item, **kwargs))
        elif isinstance(item, list):
            new.append(format_list(item, **kwargs))
    return new
