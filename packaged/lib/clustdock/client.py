# -*- coding: utf-8 -*-
'''
@author Antoine Sax <<antoine.sax@atos.net>>
@copyright 2018 Bull S.A.S.  -  All rights reserved.\n
           This is not Free or Open Source software.\n
           Please contact Bull SAS for details about its license.\n
           Bull - Rue Jean Jaures - B.P. 68 - 78340 Les Clayes-sous-Bois
@file clustdock/__init__.py
@namespace clustdock Clustdock Module
'''
import logging
import zmq
import sys
import msgpack
from ClusterShell.NodeSet import NodeSet

_LOGGER = logging.getLogger(__name__)

STATUS = {
    'created': 0,
    'running': 1,
    'paused': 3,
    'in shutdown': 4,
    'stopped': 5,
    'crashed': 6,
}
STATUS_UNKNOWN = 'unknown'


class ClustdockClient(object):
    '''Class representing the client part of the docker/libvirt architecture'''

    def __init__(self, server):
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REQ)
        self.server = server
        try:
            self.socket.connect(server)
        except zmq.error.ZMQError:
            _LOGGER.error("Could not connect to server at %s. Exiting", server)
            sys.exit(3)

    def list(self, allnodes, **kwargs):
        """Ask for nodelist on managed hosts"""
        try:
            self.socket.send("list %s" % allnodes)
            msg = self.socket.recv()
            liste = msgpack.unpackb(msg)
            print("%-10s %-7s %-40s %-11s" % ("Host", "#Nodes", "Nodeset", "Status"))
            print("-" * 71)
            liste = sort_nodes(liste)
            for host in sorted(liste):
                print('\033[01m%s\033[0m' % host)
                print_nodes(liste[host][STATUS['running']],
                            '\033[32mrunning\033[0m')
                print_nodes(liste[host][STATUS['stopped']],
                            '\033[31mstopped\033[0m')
                print_nodes(liste[host][STATUS['paused']],
                            '\033[33mpaused\033[0m')
                print_nodes(liste[host][STATUS['in shutdown']],
                            '\033[34min shutdown\033[0m')
                print_nodes(liste[host][STATUS['crashed']],
                            '\033[1;33mcrashed\033[0m')
                print_nodes(liste[host][STATUS['created']],
                            'unknown')
        except zmq.error.ZMQError:
            sys.stderr.write("Error when trying to contact server.\n")
            return 2

    def spawn(self, profil, clustername, nb_nodes, host, **kwargs):
        """Ask server to spawn a cluster"""
        rc = 0
        try:
            self.socket.send("spawn %s %s %s %s" % (profil, clustername, nb_nodes, host))
            spawn_nodes, errors = msgpack.unpackb(self.socket.recv())
            if len(errors) != 0:
                rc = 1
                for message in errors:
                    sys.stderr.write("{}\n".format(message.rstrip()))
            if spawn_nodes != "":
                print(spawn_nodes)
        except zmq.error.ZMQError:
            sys.stderr.write("Error when trying to contact server.\n")
            rc = 2
        return rc

    def stop(self, nodeset, **kwargs):
        """Ask server to stop nodeset"""
        rc = 0
        try:
            _LOGGER.debug("Trying to delete %s", nodeset)
            self.socket.send("stop_nodes %s" % nodeset)
            stopped_nodes, errors = msgpack.unpackb(self.socket.recv())
            if len(errors) != 0:
                rc = 1
                for message in errors:
                    sys.stderr.write("{}\n".format(message.rstrip()))
            if stopped_nodes != "":
                print(stopped_nodes)
        except zmq.error.ZMQError:
            sys.stderr.write("Error when trying to contact server.\n")
            rc = 2
        return rc

    def getip(self, nodeset, **kwargs):
        """Ask server to give back some ip"""
        rc = 0
        try:
            self.socket.send("get_ip %s" % nodeset)
            res, errors = msgpack.unpackb(self.socket.recv())
            if len(errors) != 0:
                rc = 1
                for message in errors:
                    sys.stderr.write(message)
            if len(res) == 1:
                print(res[0][0])
            else:
                for item in res:
                    print("{0}\t{1}".format(*item))
        except zmq.error.ZMQError:
            sys.stderr.write("Error when trying to contact server.\n")
            rc = 2
        return rc


def sort_nodes(nodelist):
    '''Sort nodes for list command'''
    hosts = {}
    for host in nodelist:
        hosts[host] = {}
        for status in STATUS.values():
            hosts[host][status] = []
        for node in nodelist[host]:
            hosts[host][node['status']].append(node['name'])
    _LOGGER.debug(hosts)
    return hosts


def print_nodes(nodes, status):
    """Print nodelist on standart output"""
    nb_nodes = len(nodes)
    if nb_nodes == 0:
        return
    nodelist = NodeSet.fromlist(nodes)
    for subset in nodelist.contiguous():
        print("{0:<10s} {1:<7d} {2:<40s} {3:<11s}".format(
              "", len(subset), str(subset), status))
