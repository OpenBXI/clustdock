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
        self.rep_sock.connect(self.url_server)
        _LOGGER.debug("worker %d connected to ThreadDevice at %s",
                      self.worker_id,
                      self.url_server)

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
        if cmd.startswith('list'):
            (_, allnodes) = cmd.split()
            hosts = self.list_nodes(allnodes=eval(allnodes), keep_obj=False)
            self.rep_sock.send(msgpack.packb(hosts))
        elif cmd.startswith('spawn'):
            (_, profil, name, nb_nodes, host) = cmd.split()
            if host == 'None':
                host = _choose_host(self.hostlist)
            if host not in self.hostlist:
                err = "Error: host '%s' is not managed" % host
                _LOGGER.error(err)
                self.rep_sock.send(msgpack.packb(("", [err])))
            else:
                nodes = self.select_nodes(profil, name, int(nb_nodes), host)
                if len(nodes) != 0:
                    self.spawn_nodes(nodes)
        elif cmd.startswith('stop_nodes'):
            nodelist = cmd.split()[1]
            self.stop_nodes(nodelist)
        elif cmd.startswith('get_ip'):
            nodelist = cmd.split()[1]
            self.get_ip(nodelist)
        else:
            _LOGGER.debug("Ignoring cmd %s", cmd)
            self.rep_sock.send(msgpack.packb('FAIL'))

    def _get_cnx(self, node):
        """return libvirt/docker connexion for given node"""
        if isinstance(node, dnode.DockerNode):
            return self._get_docker_cnx(node.host)
        elif isinstance(node, lnode.LibvirtNode):
            return self._get_libvirt_cnx(node.host)

    def _get_libvirt_cnx(self, host):
        """return libvirt connexion object"""
        cnx = self.libvirt_cnx.get(host, None)
        if cnx is None:
            _LOGGER.debug("New libvirt connexion to host '%s'", host)
            cnx = lnode.LibvirtConnexion(host)
            self.libvirt_cnx[host] = cnx
        return cnx

    def _get_docker_cnx(self, host):
        """return docker connexion object"""
        cnx = self.docker_cnx.get(host, None)
        if cnx is None:
            _LOGGER.debug("New docker connexion to host '%s'", host)
            cnx = dnode.DockerConnexion(host, self.docker_port)
            self.docker_cnx[host] = cnx
        return cnx

    def list_nodes(self, allnodes=True, hostlist=None, byhost=True, keep_obj=True):
        '''List all nodes on managed hosts or specified hostlist'''
        hosts = {}
        if hostlist is None:
            hostlist = self.hostlist
        for host in hostlist:
            libvirt_cnx = self._get_libvirt_cnx(host)
            if not libvirt_cnx.is_ok():
                _LOGGER.warning("No libvirt connexion to host %s. Skipping", host)
                continue
            vms = libvirt_cnx.listvms(allnodes=allnodes)
            if not keep_obj:
                hosts[host] = [vm.__dict__ for vm in vms]
            else:
                hosts[host] = vms
            docker_cnx = self._get_docker_cnx(host)
            if not docker_cnx.is_ok():
                _LOGGER.warning("No docker connexion to host %s. Skipping", host)
                continue
            containers = docker_cnx.list_containers(allnodes=allnodes)
            if not keep_obj:
                hosts[host].extend([dock.__dict__ for dock in containers])
            else:
                hosts[host].extend(containers)
        if not byhost:
            nodes = []
            for hostnodes in hosts.itervalues():
                nodes.extend(hostnodes)
            return nodes
        return hosts

    def get_ip(self, nodes):
        '''Get the ip of nodes if possible'''
        res = []
        errors = []
        try:
            nodeset = NodeSet(nodes)
        except NodeSetParseError:
            msg = "Error: '%s' is not a valid nodeset. Skipping" % nodes
            _LOGGER.error(msg)
            errors.append(msg)
        else:
            nodes_to_ping = []
            nodelist = self.list_nodes(allnodes=False, byhost=False)
            node_dict = {node.name: node for node in nodelist}
            availnodes = NodeSet.fromlist(node_dict.keys())
            for node in nodeset:
                if node in availnodes:
                    nodes_to_ping.append(node_dict[node])
                else:
                    msg = "Error: node '%s' does not exist or is "\
                          "not running. Skipping\n" % node
                    _LOGGER.warning(msg)
                    errors.append(msg)

            for node in nodes_to_ping:
                cnx = self._get_cnx(node)
                tmp = node.get_ip(cnx)
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
            self.rep_sock.send(msgpack.packb((nodes, [err])))
            return nodes
        if not vc.VirtualCluster.valid_clustername(name):
            err = "Error: clustername '{}' is not a valid name\n".format(name)
            _LOGGER.error(err)
            self.rep_sock.send(msgpack.packb((nodes, [err])))
            return nodes
        if profil not in self.profiles:
            err = "Error: Profil '{}' not found in configuration file\n".format(profil)
            _LOGGER.error(err)
            self.rep_sock.send(msgpack.packb((nodes, [err])))
            return nodes

        nodelist = self.list_nodes(byhost=False)
        nodeset = NodeSet.fromlist([node.name for node in nodelist])
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
                           args=(node, self._get_cnx(node)),
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

    def stop_nodes(self, nodes):
        '''Stopping nodes'''
        errors = []
        stopped_nodes = []

        try:
            nodeset = NodeSet(nodes)
        except NodeSetParseError:
            msg = "Error: '%s' is not a valid nodeset. Skipping" % nodes
            _LOGGER.error(msg)
            errors.append(msg)
        else:
            nodes_to_stop = []
            nodelist = self.list_nodes(byhost=False)
            node_dict = {node.name: node for node in nodelist}
            availnodes = NodeSet.fromlist(node_dict.keys())
            for node in nodeset:
                if node in availnodes:
                    nodes_to_stop.append(node_dict[node])
                else:
                    msg = "Error: node '%s' does not exist. Skipping" % node
                    _LOGGER.warning(msg)
                    errors.append(msg)

            processes = []
            for node in nodes_to_stop:
                to_child, to_self = mp.Pipe()
                p = mp.Process(target=node.__class__.stop,
                               args=(node, self._get_cnx(node)),
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
    if 'docker_opts' in dico:
        return clustdock.docker_node.DockerNode(**dico)
    elif 'base_domain' in dico:
        return clustdock.libvirt_node.LibvirtNode(**dico)
    else:
        return dico
