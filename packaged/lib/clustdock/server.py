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
import random
import multiprocessing as mp
from ClusterShell.NodeSet import NodeSet
from ClusterShell.NodeSet import NodeSetBase
from ClusterShell.RangeSet import RangeSet
from ClusterShell.NodeSet import NodeSetParseError
import clustdock.virtual_cluster as vc
import clustdock.docker_node as dnode
import clustdock.libvirt_node as lnode
import clustdock

_LOGGER = logging.getLogger(__name__)
# IPC_SOCK = "ipc:///var/run/clustdock_workers.sock"
IPC_SOCK = "ipc:///tmp/clustdock_workers.sock"


class ClustdockWorker(object):

    def __init__(self, url_server, worker_id, profiles, hostlist, docker_port):
        self.worker_id = worker_id
        self.url_server = url_server
        self.profiles = profiles
        self.hostlist = hostlist
        self.libvirt_cnx = {}
        self.docker_cnx = {}
        self.docker_port = docker_port

    def init_sockets(self):
        """Initialize zmq sockets"""
        _LOGGER.info("Initializing sockets for worker %d", self.worker_id)
        self.ctx = zmq.Context()
        self.rep_sock = self.ctx.socket(zmq.REP)
        _LOGGER.debug("trying to connect worker %d to ThreadDevice at %s",
                      self.worker_id,
                      self.url_server)
        self.rep_sock.connect(self.url_server)
        _LOGGER.debug("trying to connect worker %d to server at %s",
                      self.worker_id,
                      IPC_SOCK)

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
                        _LOGGER.debug("cmd '%s' processed", cmd)
                    if fo.fileno() in items:
                        _LOGGER.debug("Signal received on worker %d", self.worker_id)
                        break
                except KeyboardInterrupt:
                    _LOGGER.debug("Keyboard interrrupt received on worker %d", self.worker_id)
                    break
        _LOGGER.debug("Stopping worker %d", self.worker_id)
        self.rep_sock.close()

    def process_cmd(self, cmd):
        '''Process recieved cmd'''
        if cmd == 'list':
            hosts = self.list_nodes()
            self.rep_sock.send(msgpack.packb(hosts))
        elif cmd.startswith('spawn'):
            (_, profil, name, nb_nodes, host) = cmd.split()
            if host == 'None':
                host = _choose_host(self.hostlist)
            nodes = self.select_nodes(profil, name, int(nb_nodes), host)
            if len(nodes) != 0:
                self.spawn_nodes(nodes)
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

    def _get_libvirt_cnx(self, host):
        """return libvirt connexion object"""
        cnx = self.libvirt_cnx.get(host, None)
        if cnx is None:
            cnx = lnode.LibvirtConnexion(host)
            self.libvirt_cnx[host] = cnx
        return cnx

    def _get_docker_cnx(self, host):
        """return docker connexion object"""
        cnx = self.docker_cnx.get(host, None)
        if cnx is None:
            cnx = dnode.DockerConnexion(host, self.docker_port)
            self.docker_cnx[host] = cnx
        return cnx

    def list_nodes(self, hostlist=None, byhost=True):
        '''List all nodes on managed hosts or specified hostlist'''
        hosts = {}
        if hostlist is None:
            hostlist = self.hostlist
        for host in hostlist:
            libvirt_cnx = self._get_libvirt_cnx(host)
            if not libvirt_cnx.is_ok():
                _LOGGER.warning("No libvirt connexion to host %s. Skipping", host)
                continue
            vms = libvirt_cnx.listvms()
            hosts[host] = [vm.__dict__ for vm in vms]
            docker_cnx = self._get_docker_cnx(host)
            if not docker_cnx.is_ok():
                _LOGGER.warning("No docker connexion to host %s. Skipping", host)
                continue
            containers = docker_cnx.list_containers()
            hosts[host].extend([dock.__dict__ for dock in containers])
        if not byhost:
            nodes = []
            for hostnodes in hosts.itervalues():
                nodes.extend(hostnodes)
            return nodes
        return hosts

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
    
    def select_nodes(self, profil, name, nb_nodes, host):
        '''Select nodes to spawn'''
        # 1: recover available nodelist
        # 2: select nb_nodes among availables nodes
        # 3: return the list of nodes
        err = ""
        nodes = []
        if host is None:
            err = "Error: No host available\n"
            _LOGGER.error(err)
            self.rep_sock.send(msgpack.packb((nodes, err)))
            return nodes
        if not vc.VirtualCluster.valid_clustername(name):
            err = "Error: clustername '{}' is not a valid name\n".format(name)
            _LOGGER.error(err)
            self.rep_sock.send(msgpack.packb((nodes, err)))
            return nodes
        if profil not in self.profiles:
            err = "Error: Profil '{}' not found in configuration file\n".format(profil)
            _LOGGER.error(err)
            self.rep_sock.send(msgpack.packb((nodes, err)))
            return nodes

        nodelist = self.list_nodes(byhost=False)
        nodeset = NodeSet.fromlist([node['name'] for node in nodelist])
        idx_min = 0
        idx_max = nb_nodes - 1
        base_range = RangeSet("%d-%d" % (idx_min, idx_max))
        base_nodeset = NodeSetBase(name + '%s', base_range)
        ndset_inter = nodeset.intersection(base_nodeset)
        while len(ndset_inter) != 0:
            indexes = [clustdock.VirtualNode.split_name(node)[1] for node in ndset_inter]
            for idx in indexes:
                _LOGGER.debug("Removing %d from rangeset %s", idx, base_range)
                base_range.remove(idx)
            base_nodeset.difference_update(ndset_inter)
            _LOGGER.debug("Nodeset becomes '%s' after removing", base_nodeset)
            idx_min = max(indexes + list(base_range)) + 1
            idx_max = idx_min + max([len(indexes), nb_nodes - len(base_range)])
            base_range.add_range(idx_min, idx_max)
            _LOGGER.debug("New rangeset: %s", base_range)
            base_nodeset.update(NodeSetBase(name + '%s',
                                RangeSet.fromlist([range(idx_min, idx_max)])))
            _LOGGER.debug("New nodeset: %s", base_nodeset)
            ndset_inter = nodeset.intersection(base_nodeset)

        final_range = base_range
        _LOGGER.debug("final rangeset/nodeset: %s / %s", base_range, base_nodeset)

        cluster = vc.VirtualCluster(name, profil, self.profiles[profil])
        nodes = []
        for idx in final_range:
            node = cluster.add_node(idx, host)
            nodes.append(node)
        return nodes

    def spawn_nodes(self, nodes):
        '''Spawn some nodes'''
        errors = []
        processes = []
        for node in nodes:
            to_child, to_self = mp.Pipe()
            p = mp.Process(target=node.__class__.start,
                           args=(node,),
                           kwargs={'pipe': to_self})
            p.start()
            processes.append((node, p, (to_child, to_self)))
        spawned_nodes = []
        nodes_to_del = []
        for node, p, pipes in processes:
            p.join()
            if p.exitcode == 0:
                spawned_nodes.append(node.name)
            else:
                nodes_to_del.append(node.name)
                err = pipes[0].recv()
                errors.append(err)
            pipes[0].close()
            pipes[1].close()

        _LOGGER.debug(spawned_nodes)
        nodelist = str(NodeSet.fromlist(spawned_nodes))
        errors_nodelist = str(NodeSet.fromlist(nodes_to_del))
        self.rep_sock.send(msgpack.packb((nodelist, errors)))

    def stop_nodes(self, nodes, err):
        '''Stopping nodes'''
        errors = []
        if err != "":
            errors.append(err)
        processes = []
        stopped_nodes = []
        for node in nodes:
            to_child, to_self = mp.Pipe()
            p = mp.Process(target=node.__class__.stop,
                           args=(node,),
                           kwargs={'pipe': to_self})
            p.start()
            processes.append((node, p, (to_child, to_self)))

        for node, p, pipes in processes:
            p.join()
            if p.exitcode == 0:
                stopped_nodes.append(node.name)
            else:
                errors.append(pipes[0].recv())
            pipes[0].close()
            pipes[1].close()

        nodelist = str(NodeSet.fromlist(stopped_nodes))
        self.rep_sock.send(msgpack.packb((nodelist, errors)))

















class ClustdockServer(object):

    def __init__(self, port, profiles, dump_file, hosts):
        '''docstring'''
        self.port = port
        self.profiles = profiles
        self.dump_file = dump_file
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REP)
        _LOGGER.debug("Trying to bind server to %s", IPC_SOCK)
        self.socket.bind(IPC_SOCK)
        self.hosts = extract_hosts(hosts)

    def process_cmd(self, cmd, worker_id):
        '''Process cmd received by a worker'''
        if cmd.startswith('list'):
            self.socket.send(msgpack.packb(self.clusters.values(),
                             default=encode_cluster))
        elif cmd.startswith('spawn'):
            (_, profil, name, nb_nodes, host) = cmd.split()
            if host == 'None':
                host = _choose_host(self.hosts)
            self.create_nodes(profil, name, int(nb_nodes), host, worker_id)
        elif cmd.startswith('del_nodes'):
            name = cmd.split()[1]
            self.del_nodes(name, worker_id)
        elif cmd.startswith('started_nodes'):
            nodelist = cmd.split()[1]
            self.started_nodes(nodelist, worker_id)
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
        if host is None:
            err = "Error: No host available\n"
            _LOGGER.error(err)
            self.socket.send(msgpack.packb((nodes, err)))
            return
        if not vc.VirtualCluster.valid_clustername(name):
            err = "Error: clustername '{}' is not a valid name\n".format(name)
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

    def started_nodes(self, nodelist, worker_id):
        '''Maj status of nodes'''
        nodes, res = self.get_nodes(nodelist)
        for node in nodes:
            _LOGGER.debug("Maj status for node %s to STARTED", node.name)
            cluster = self.clusters.get(node.clustername, None)
            self.clusters[cluster.name].nodes[node.name].status = clustdock.VirtualNode.STATUS_STARTED
        self.socket.send(msgpack.packb('OK'))

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
                try:
                    clustername, _ = clustdock.VirtualNode.split_name(nodename)
                except AttributeError:
                    _LOGGER.error("%s is not a valid node name", nodename)
                    res += "Error: '{}' is not a valid node name\n".format(nodename)
                    continue
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


def extract_hosts(hosts):
    """Extracting list of managed hosts from nodeset"""
    nodeset = NodeSet()
    if isinstance(hosts, list) or isinstance(hosts, tuple):
        nodeset = NodeSet.fromlist(hosts)
    else:
        nodeset = NodeSet(hosts)
    return nodeset


def _choose_host(hosts):
    """Choose random host in hostlist"""
    host = None
    try:
        host = random.choice(hosts)
    except (TypeError, IndexError):
        _LOGGER.error("Empty hostlist given: %s", hosts)
    return host


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


def sort_nodes(cluster):
    '''Sort nodes for list command'''
    hosts = {}

    for nodename in cluster.nodes:
        node = cluster.nodes[nodename]
        if node.host not in hosts:
            hosts[node.host] = {
                cluster.name: {
                    clustdock.VirtualNode.STATUS_STARTED: [],
                    clustdock.VirtualNode.STATUS_UNREACHABLE: [],
                    clustdock.VirtualNode.STATUS_UNKNOWN: []
                }
            }
        hosts[node.host][cluster.name][node.status].append(node.name)
    return hosts
