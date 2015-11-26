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
import logging
import zmq
import sys
import msgpack

_LOGGER = logging.getLogger(__name__)


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

    def list(self, **kwargs):
        try:
            self.socket.send("list")
            msg = self.socket.recv()
            liste = msgpack.unpackb(msg)
            # print("%-10s %-7s %-20s %-40s" % ("Cluster", "#Nodes", "Nodeset", "Hosts"))
            print("%-7s %-20s %-40s" % ("#Nodes", "Nodeset", "Hosts"))
            print("-" * 77)
            for item in liste:
                # print("{0:<10s} {1:<7d} {2:<20s} {3:<40s}".format(*item))
                print("{1:<7d} {2:<20s} {3:<40s}".format(*item))
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
                    sys.stderr.write(message)
            if spawn_nodes != "":
                print(spawn_nodes)
        except zmq.error.ZMQError:
            sys.stderr.write("Error when trying to contact server.\n")
            rc = 2
        return rc

    def stop(self, nodeset, **kwargs):
        """docstring"""
        rc = 0
        try:
            _LOGGER.debug("Trying to delete %s", nodeset)
            self.socket.send("stop_nodes %s" % nodeset)
            stopped_nodes, errors = msgpack.unpackb(self.socket.recv())
            if len(errors) != 0:
                rc = 1
                for message in errors:
                    sys.stderr.write(message)
            if stopped_nodes != "":
                print(stopped_nodes)
        except zmq.error.ZMQError:
            sys.stderr.write("Error when trying to contact server.\n")
            rc = 2
        return rc

    def getip(self, nodeset, **kwargs):
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
