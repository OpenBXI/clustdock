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
import subprocess as sp

DOCKER_NODE = "docker"
LIBVIRT_NODE = "libvirt"

_LOGGER = logging.getLogger(__name__)


class VirtualNode(object):
    '''Represents a virtual node'''

    STATUS_STARTED = 1
    STATUS_UNREACHABLE = 2
    STATUS_UNKNOWN = 3

    def __init__(self, name, host=None, ip=None, **kwargs):
        self.name = name
        self.ip = ip if ip is not None else ''
        if host:
            self.host = host
        else:
            self.host = 'localhost'
        self.status = kwargs.get('status', self.STATUS_UNKNOWN)
        self.clustername, self.idx = VirtualNode.split_name(self.name)
        self.unreachable = False
        self.before_start = kwargs.get('before_start', None)
        self.after_start = kwargs.get('after_start', None)
        self.after_end = kwargs.get('after_end', None)
        self.add_iface = kwargs.get('add_iface', None)

    @classmethod
    def split_name(cls, nodename):
        res = re.search(r'^([a-z]+[a-z-_]+)(\d+)$', nodename)
        clustername = nodename
        idx = None
        if res is not None:
            grp = res.groups()
            clustername = grp[0]
            idx = int(grp[1])
        return (clustername, idx)

    def run_hook(self, hook_file, vtype):
        """Run hook-file"""
        cmd = "%s %s %s %s" % (hook_file,
                               self.name,
                               vtype,
                               self.host)
        p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        (stdout, stderr) = p.communicate()
        return (p.returncode, stdout, stderr)

    def start(self, pipe):
        """Start virtual node"""
        raise NotImplementedError("Must be redefine is subclasses")

    def stop(self, pipe=None, fork=True):
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
