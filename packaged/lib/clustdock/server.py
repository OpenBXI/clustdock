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
import cPickle
import msgpack
import multiprocessing as mp
from ClusterShell.NodeSet import NodeSet
from ClusterShell.NodeSet import NodeSetParseError
import clustdock.virtual_cluster as vc
import clustdock

DUMP_FILE = "/var/run/clustdockd.bin"
_LOGGER = logging.getLogger(__name__)


class ClustdockServer(object):

    def __init__(self, port, profiles):
        '''docstring'''
        self.port = port
        self.profiles = profiles
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.ROUTER)
        _LOGGER.debug("trying to bind socket to port %s", port)
        self.socket.bind("tcp://*:%s" % port)
        self.clusters = dict()

    def load_from_file(self):
        """Load cluster list from file"""
        try:
            with open(DUMP_FILE, 'r') as dump_file:
                self.clusters = cPickle.load(dump_file)
        except IOError:
            _LOGGER.debug("File %s doesn't exists. Skipping load from file.", DUMP_FILE)
        except (cPickle.PickleError, AttributeError):
            _LOGGER.debug("Error when loading clusters from file")

    def save_to_file(self):
        """Save cluster list to file"""
        try:
            with open(DUMP_FILE, 'w') as dump_file:
                cPickle.dump(self.clusters, dump_file)
        except IOError:
            _LOGGER.debug("Cannot write to file %s. Skipping", DUMP_FILE)
        except cPickle.PickleError:
            _LOGGER.debug("Error when saving clusters to file")

    def inventory(self):
        _LOGGER.info("Inventory of clusters")
        for cluster in self.clusters.values():
            for node in cluster.nodes.values():
                if not node.is_alive():
                    _LOGGER.info("Deleting node %s", node.name)
                    del cluster.nodes[node.name]
            _LOGGER.info("Cluster %s, #Nodes: %d, Nodes: %s", cluster.name,
                                                              cluster.nb_nodes,
                                                              cluster.nodeset)
            if len(cluster.nodes) == 0:
                _LOGGER.info("Deleting cluster %s", cluster.name)
                del self.clusters[cluster.name]

    def process_cmd(self, cmd, clientid):
        '''Process cmd received by a client'''
        if cmd == 'list':
            self.list_clusters(clientid)
        elif cmd.startswith('spawn'):
            (_, profil, name, nb_nodes, host) = cmd.split()
            if host == 'None':
                host = None
            self.spawn_cluster(profil, name, int(nb_nodes), host, clientid)
        elif cmd.startswith('del_node'):
            name = cmd.split()[1]
            self.del_node(name, clientid)
        elif cmd.startswith('get_ip'):
            name = cmd.split()[1]
            self.get_ip(name, clientid)
        else:
            _LOGGER.debug("Ignoring cmd %s", cmd)
            self.socket.send_multipart([clientid, '', msgpack.packb('FAIL')])

    def list_clusters(self, clientid):
        '''List all clusters'''
        mylist = []
        for cluster in self.clusters.values():
            mylist.append((cluster.name, len(cluster.nodes),
                           cluster.nodeset, cluster.byhosts()))

        self.socket.send_multipart([clientid, '', msgpack.packb(mylist)])

    def spawn_cluster(self, profil, name, nb_nodes, host, clientid):
        '''Spawn a cluster'''
        # 1: Check if cluster $name exists
        # 2: if yes, then
        #       get already spawned nodes
        # 3: select nb_nodes among availables nodes
        # 4: make those nodes not usable for future clients
        # 5: return the list of nodes to the client
        # _LOGGER.debug("len cluster.nodes: %d", len(VirtualCluster.clusters[name].nodes))
        err = []

        if not vc.VirtualCluster.valid_clustername(name):
            msg = "Error: clustername '{}' is not a valid name." + \
                  " It must only contains lowercase letters or '-_' characters".format(name)
            err.append(msg)
            _LOGGER.error(msg)
            self.socket.send_multipart([clientid, '', msgpack.packb(err)])
            return

        if name in self.clusters:
            cluster = self.clusters[name]
        elif profil in self.profiles:
            cluster = vc.VirtualCluster(name, self.profiles[profil])
            self.clusters[cluster.name] = cluster
        else:
            msg = "Error: Profil '{}' not found in configuration file".format(profil)
            err.append(msg)
            _LOGGER.error(msg)
            self.socket.send_multipart([clientid, '', msgpack.packb(err)])
            return

        # Cluster defined, can continue
        _LOGGER.debug("len cluster.nodes: %d", len(cluster.nodes))
        indexes = [node.idx for node in cluster.nodes.itervalues()]
        _LOGGER.debug("indexes : %s", indexes)
        if len(indexes) == 0:
            idx_min = -1
            idx_max = -1
        else:
            idx_min = min(indexes)
            idx_max = max(indexes)
        if (idx_min == idx_max == -1):
            selected_range = range(0, nb_nodes)
        elif (idx_min - nb_nodes) >= 0:
            selected_range = range(idx_min - nb_nodes, idx_min)
        else:
            selected_range = range(idx_max + 1, idx_max + 1 + nb_nodes)

        processes = []
        for idx in selected_range:
            node = cluster.add_node(idx, host)
            p = mp.Process(target=node.__class__.start, args=(node,))
            p.start()
            processes.append((node.name, p))
        spawned_nodes = []
        for node_name, p in processes:
            p.join()
            if p.exitcode == 0:
                spawned_nodes.append(node_name)
            else:
                del cluster.nodes[node_name]
                err.append("Error when spawning %s" % node_name)

        if len(cluster.nodes) == 0:
            del self.clusters[cluster.name]

        _LOGGER.debug(spawned_nodes)
        nodelist = str(NodeSet.fromlist(spawned_nodes))
        err.append(nodelist)
        self.socket.send_multipart([clientid, '', msgpack.packb(err)])

    def get_ip(self, name, clientid):
        '''Get the ip of a node if possible'''
        nodeset = NodeSet(name)
        res = []
        for nodename in nodeset:
            ip = "Unable to find IP for node %s" % nodename
            clustername, _ = clustdock.VirtualNode.split_name(nodename)
            cluster = self.clusters.get(clustername, None)
            if cluster:
                node = cluster.nodes.get(nodename, None)
                if node:
                    tmp = node.get_ip()
                    if tmp != '':
                        ip = tmp
            res.append((ip, nodename))
        self.socket.send_multipart([clientid, '', msgpack.packb(res)])

    def del_node(self, name, clientid):
        '''Delete node'''
        res = ""
        try:
            nodeset = NodeSet(name)
        except NodeSetParseError:
            res = "Error: '%s' is not a valid nodeset. Skipping" % name
            _LOGGER.error(res)
        else:
            processes = []
            for nodename in nodeset:
                clustername, _ = clustdock.VirtualNode.split_name(nodename)
                cluster = self.clusters.get(clustername, None)
                if cluster:
                    node = cluster.nodes.get(nodename, None)
                    if node:
                        _LOGGER.debug("deleting node %s", node.name)
                        p = mp.Process(target=node.__class__.stop, args=(node,))
                        p.start()
                        processes.append((cluster, node.name, p))
                    else:
                        _LOGGER.debug("Node %s doesn't exists. Perhaps something went wrong",
                                  nodename)
                        res += "Error: Node %s doesn't exist\n" % nodename
                else:
                    _LOGGER.debug("Cluster %s doesn't exists. Perhaps something went wrong",
                                  clustername)
                    res += "Error: Cluster %s doesn't exist\n" % clustername
            stopped_nodes = []
            for cluster, node_name, p in processes:
                p.join()
                if p.exitcode == 0:
                    stopped_nodes.append(node_name)
                    del cluster.nodes[node_name]

            for cluster in set([item[0] for item in processes]):
                if len(cluster.nodes) == 0:
                    _LOGGER.debug("Deleting cluster %s", cluster.name)
                    del self.clusters[cluster.name]

            nodelist = str(NodeSet.fromlist(stopped_nodes))
            _LOGGER.debug("Stopped nodes: %s", nodelist)
            res += "Stopped nodes: %s" % nodelist if nodelist != "" else ""
        self.socket.send_multipart([clientid, '', msgpack.packb(res)])
