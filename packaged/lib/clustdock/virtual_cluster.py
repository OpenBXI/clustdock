# -*- coding: utf-8 -*-
'''
@author Antoine Sax <<antoine.sax@atos.net>>
@copyright 2018 Bull S.A.S.  -  All rights reserved.\n
           This is not Free or Open Source software.\n
           Please contact Bull SAS for details about its license.\n
           Bull - Rue Jean Jaures - B.P. 68 - 78340 Les Clayes-sous-Bois
@file clustdock/libvirt_node.py
@namespace clustdock.libvirt_node LibvirtNode definition
'''
import logging
import re
from ClusterShell.NodeSet import NodeSet
from ClusterShell.RangeSet import RangeSet
from ClusterShell.RangeSet import RangeSetParseError
import clustdock
import clustdock.docker_node as dock
import clustdock.libvirt_node as lbv

_LOGGER = logging.getLogger(__name__)


class VirtualCluster(object):
    '''Represents a docker cluster'''

    def __init__(self, name, profil, cfg, **kwargs):
        self.name = name
        self.nodes = dict()
        self.profil = profil
        self.cfg = self._extract_conf(cfg)

    @classmethod
    def valid_clustername(cls, name):
        '''Test if the name is a valid clustername'''
        try:
            re.search(r'^([a-z]+[a-z-_]+)$', name).groups()
            return True
        except AttributeError:
            return False

    @property
    def nb_nodes(self):
        return len(self.nodes)

    @property
    def nodeset(self):
        return str(NodeSet.fromlist(self.nodes.keys()))

    def _extract_conf(self, cfg):
        """Extract cluster nodes configuration"""
        conf = {
            "default": {
            }
        }
        for key, val in cfg.iteritems():
            if key == 'default':
                conf['default'].update(val)
            elif isinstance(val, dict):
                if isinstance(key, int):
                    rset = RangeSet.fromone(key)
                else:
                    try:
                        rset = RangeSet(key)
                    except RangeSetParseError as err:
                        _LOGGER.warning("Error in configuration file:"
                                        " %s. Ingnoring this part", err)
                        continue
                for idx in rset:
                    conf[idx] = val
            else:
                conf['default'][key] = val
        try:
            conf = clustdock.format_dict(conf, **self.__dict__)
        except KeyError:
            _LOGGER.exception("Key not found:")
        return conf

    def add_node(self, idx, host):
        """Create new node on host and add it to the cluster"""
        self.cfg['default']['host'] = host
        conf = self.cfg['default'].copy()
        conf.update(self.cfg.get(idx, {}))
        _LOGGER.debug(conf)
        if conf['vtype'] == clustdock.DOCKER_NODE:
            node = dock.DockerNode("%s%d" % (self.name, idx), **conf)
        elif conf['vtype'] == clustdock.LIBVIRT_NODE:
            node = lbv.LibvirtNode("%s%d" % (self.name, idx), **conf)
        self.nodes[node.name] = node
        return node

    def byhosts(self):
        """Return string describing on which hosts are virtual nodes"""
        byhost = {}
        for node in self.nodes.values():
            if node.host not in byhost:
                byhost[node.host] = NodeSet(node.name)
            else:
                byhost[node.host].add(node.name)
        return " - ".join([k + ':' + str(byhost[k]) for k in byhost])
