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
import signalfd
import signal
import os
import multiprocessing as mp
from ClusterShell.NodeSet import NodeSet
from ClusterShell.NodeSet import NodeSetParseError
import clustdock.virtual_cluster as vc
import clustdock.docker_node
import clustdock.libvirt_node
import clustdock

DUMP_FILE = "/var/run/clustdockd.bin"
_LOGGER = logging.getLogger(__name__)
IPC_SOCK = "ipc:///var/run/clustdock_workers.sock"


class ClustdockWorker(object):

    def __init__(self, url_server, worker_id):
        self.worker_id = worker_id
        self.url_server = url_server

    def init_sockets(self):
        """Initialize zmq sockets"""
        _LOGGER.info("Initializing sockets for worker %d", self.worker_id)
        self.ctx = zmq.Context()
        self.rep_sock = self.ctx.socket(zmq.REP)
        self.req_sock = self.ctx.socket(zmq.REQ)
        _LOGGER.debug("trying to connect worker %d to ThreadDevice at %s",
                      self.worker_id,
                      self.url_server)
        self.rep_sock.connect(self.url_server)
        _LOGGER.debug("trying to connect worker %d to server at %s",
                      self.worker_id,
                      IPC_SOCK)
        self.req_sock.connect(IPC_SOCK)

    def start(self, loglevel, logfile):
        """Start to work !"""
        logging.basicConfig(level=loglevel,
        stream=logfile,
        format="%(levelname)s|%(asctime)s|%(process)d|%(filename)s|%(funcName)s|%(lineno)d| %(message)s")
        global _LOGGER
        _LOGGER = logging.getLogger(__name__)
        self.init_sockets()
        _LOGGER.debug("Worker %d started", self.worker_id)
        fd = signalfd.signalfd(-1, [signal.SIGTERM], signalfd.SFD_CLOEXEC)
        signalfd.sigprocmask(signalfd.SIG_BLOCK, [signal.SIGTERM])
        with os.fdopen(fd) as fo:
            poller = zmq.Poller()
            poller.register(self.rep_sock, zmq.POLLIN)
            poller.register(fo, zmq.POLLIN)
            while True:
                try:
                    items = dict(poller.poll(1000))
                    if self.rep_sock in items:
                        cmd = self.rep_sock.recv()
                        _LOGGER.debug("cmd received from client: '%s'", cmd)
                        self.process_cmd(cmd)
                    if fo.fileno() in items:
                        _LOGGER.debug("Signal received on worker %d", self.worker_id)
                        break
                except KeyboardInterrupt:
                    _LOGGER.debug("Keyboard interrrupt received on worker %d", self.worker_id)
                    break
        _LOGGER.debug("Stopping worker %d", self.worker_id)
        self.rep_sock.close()
        self.req_sock.close()

    def process_cmd(self, cmd):
        '''Process recieved cmd'''
        if cmd == 'list':
            self.list_clusters()
        elif cmd.startswith('spawn'):
            self.req_sock.send('%d %s' % (self.worker_id, cmd))
            rep = self.req_sock.recv()
            (nodes, res) = msgpack.unpackb(rep, object_hook=decode_node)
            self.spawn_nodes(nodes, res)
        elif cmd.startswith('stop_nodes'):
            nodelist = cmd.split()[1]
            self.req_sock.send('%d del_nodes %s' % (self.worker_id, nodelist))
            rep = self.req_sock.recv()
            (nodes, res) = msgpack.unpackb(rep, object_hook=decode_node)
            self.stop_nodes(nodes, res)
        elif cmd.startswith('get_ip'):
            nodelist = cmd.split()[1]
            self.req_sock.send('%d get_nodes %s' % (self.worker_id, nodelist))
            rep = self.req_sock.recv()
            (nodes, res) = msgpack.unpackb(rep, object_hook=decode_node)
            self.get_ip(nodes, res)
        else:
            _LOGGER.debug("Ignoring cmd %s", cmd)
            self.rep_sock.send(msgpack.packb('FAIL'))

    def list_clusters(self):
        '''List all clusters'''
        mylist = []
        self.req_sock.send('%d list' % self.worker_id)
        rep = self.req_sock.recv()
        clusters = msgpack.unpackb(rep, object_hook=decode_cluster)
        for cluster in clusters:
            mylist.append((cluster.name, len(cluster.nodes),
                           cluster.nodeset, cluster.byhosts()))
        self.rep_sock.send(msgpack.packb(mylist))

    def get_ip(self, nodes, err):
        '''Get the ip of a node if possible'''
        res = []
        errors = []
        if err != "":
            errors.append(err)
        for node in nodes:
            tmp = node.get_ip()
            if tmp != '':
                res.append((tmp, node.name))
            else:
                errors.append("Error: Unable to find IP for node %s\n" % node.name)
        self.rep_sock.send(msgpack.packb((res, errors)))

    def spawn_nodes(self, nodes, err):
        '''Spawn some nodes'''
        errors = []
        if err != "":
            errors.append(err)
        processes = []
        for node in nodes:
            p = mp.Process(target=node.__class__.start, args=(node,))
            p.start()
            processes.append((node, p))
        spawned_nodes = []
        nodes_to_del = []
        for node, p in processes:
            p.join()
            if p.exitcode == 0:
                spawned_nodes.append(node.name)
            else:
                nodes_to_del.append(node.name)

        _LOGGER.debug(spawned_nodes)
        nodelist = str(NodeSet.fromlist(spawned_nodes))
        errors_nodelist = str(NodeSet.fromlist(nodes_to_del))
        if len(nodes_to_del) != 0:
            errors.append("Error: unable to spawn %s nodes" % errors_nodelist)
        self.rep_sock.send(msgpack.packb((nodelist, errors)))

        # Send the list of non-spawn nodes to the server for deletion
        if len(nodes_to_del) != 0:
            self.req_sock.send("%d del_nodes %s" % (
                               self.worker_id,
                               errors_nodelist))
            # Wait for reply
            self.req_sock.recv()

    def stop_nodes(self, nodes, err):
        '''Stopping nodes'''
        errors = []
        if err != "":
            errors.append(err)
        processes = []
        stopped_nodes = []
        err = []
        for node in nodes:
            _LOGGER.debug("stopping node %s", node.name)
            p = mp.Process(target=node.__class__.stop, args=(node,))
            p.start()
            processes.append((node, p))

        for node, p in processes:
            p.join()
            if p.exitcode == 0:
                stopped_nodes.append(node.name)
            else:
                err.append(node.name)

        nodelist = str(NodeSet.fromlist(stopped_nodes))
        errors_nodelist = str(NodeSet.fromlist(err))
        errors.append(errors_nodelist)
        self.rep_sock.send(msgpack.packb((nodelist, errors)))


class ClustdockServer(object):

    def __init__(self, port, profiles):
        '''docstring'''
        self.port = port
        self.profiles = profiles
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REP)
        _LOGGER.debug("Trying to bind server to %s", IPC_SOCK)
        self.socket.bind(IPC_SOCK)
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

    def process_cmd(self, cmd, worker_id):
        '''Process cmd received by a worker'''
        if cmd.startswith('list'):
            self.socket.send(msgpack.packb(self.clusters.values(),
                             default=encode_cluster))
        elif cmd.startswith('spawn'):
            (_, profil, name, nb_nodes, host) = cmd.split()
            if host == 'None':
                host = None
            self.create_nodes(profil, name, int(nb_nodes), host, worker_id)
        elif cmd.startswith('del_nodes'):
            name = cmd.split()[1]
            self.del_nodes(name, worker_id)
        elif cmd.startswith('get_nodes'):
            nodelist = cmd.split()[1]
            nodes, res = self.get_nodes(nodelist)
            self.socket.send(msgpack.packb((nodes, res), default=encode_node))
        else:
            _LOGGER.debug("Ignoring cmd %s from worker %s", cmd, worker_id)
            self.socket.send(msgpack.packb('FAIL'))

    def create_nodes(self, profil, name, nb_nodes, host, clientid):
        '''Spawn a cluster'''
        # 1: Check if cluster $name exists
        # 2: if yes, then
        #       get already spawned nodes
        # 3: select nb_nodes among availables nodes
        # 4: make those nodes not usable for future clients
        # 5: return the list of nodes to the client
        err = ""
        nodes = []
        if not vc.VirtualCluster.valid_clustername(name):
            err = "Error: clustername '{}' is not a valid name." + \
                  " It must only contains lowercase letters or '-_' characters\n".format(name)
            _LOGGER.error(err)
            self.socket.send(msgpack.packb((nodes, err)))
            return

        if profil in self.profiles:
            if name in self.clusters:
                cluster = self.clusters[name]
                if cluster.profil != profil:
                    err = "Error: Cluster '{0}' already " \
                          "created with '{1}' profil\n".format(cluster.name,
                                                               cluster.profil)
                    _LOGGER.error(err)
            else:
                cluster = vc.VirtualCluster(name, profil, self.profiles[profil])
                self.clusters[cluster.name] = cluster
        else:
            err = "Error: Profil '{}' not found in configuration file\n".format(profil)
            _LOGGER.error(err)
        if err != "":
            self.socket.send(msgpack.packb((nodes, err)))
            return

        # Cluster defined, can continue
        indexes = [node.idx for node in cluster.nodes.itervalues()]
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

        nodes = []
        for idx in selected_range:
            node = cluster.add_node(idx, host)
            nodes.append(node)

        self.socket.send(msgpack.packb((nodes, err), default=encode_node))

    def del_nodes(self, nodelist, worker_id):
        '''Delete node'''
        deleted_nodes = []
        nodes, res = self.get_nodes(nodelist)
        for node in nodes:
            cluster = self.clusters.get(node.clustername, None)
            _LOGGER.debug("deleting node %s", node.name)
            del cluster.nodes[node.name]
            deleted_nodes.append(node.name)
            if len(cluster.nodes) == 0:
                _LOGGER.debug("Deleting cluster %s", cluster.name)
                del self.clusters[cluster.name]
        self.socket.send(msgpack.packb((nodes, res), default=encode_node))

    def get_nodes(self, nodelist):
        """Return object representation of nodes in nodelist"""
        nodes = []
        res = ""
        try:
            nodeset = NodeSet(nodelist)
        except NodeSetParseError:
            res = "Error: '%s' is not a valid nodeset. Skipping" % nodelist
            _LOGGER.error(res)
        else:
            for nodename in nodeset:
                clustername, _ = clustdock.VirtualNode.split_name(nodename)
                cluster = self.clusters.get(clustername, None)
                if cluster:
                    node = cluster.nodes.get(nodename, None)
                    if node:
                        nodes.append(node)
                    else:
                        _LOGGER.debug("Node %s does not exist", nodename)
                        res += "Error: Node %s does not exist\n" % nodename
                else:
                    _LOGGER.debug("Cluster %s does not exist", clustername)
                    res += "Error: Cluster %s does not exist\n" % clustername

            return (nodes, res)


def encode_node(obj):
    """Prepare node to be send over the network"""
    if isinstance(obj, clustdock.VirtualNode):
        return obj.__dict__
    else:
        return obj


def decode_node(dico):
    """Recreate node from dict"""
    if 'docker_host' in dico:
        return clustdock.docker_node.DockerNode(**dico)
    elif 'uri' in dico:
        return clustdock.libvirt_node.LibvirtNode(**dico)
    else:
        return dico


def encode_cluster(obj):
    """Prepare cluster to be send over the network"""
    if isinstance(obj, vc.VirtualCluster):
        nodes_desc = {}
        for node in obj.nodes:
            node_desc = encode_node(obj.nodes[node])
            nodes_desc[node] = node_desc
        encoded = obj.__dict__.copy()
        encoded['nodes'] = nodes_desc
        return encoded
    else:
        return obj


def decode_cluster(dico):
    """Recreate node from dict"""
    if 'nodes' in dico:
        cluster = vc.VirtualCluster(**dico)
        for node_name in dico['nodes']:
            node = decode_node(dico['nodes'][node_name])
            cluster.nodes[node.name] = node
        return cluster
    else:
        return dico
