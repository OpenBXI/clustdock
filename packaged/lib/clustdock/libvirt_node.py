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
import sys
import os
import subprocess as sp
from lxml import etree
import libvirt
import clustdock

_LOGGER = logging.getLogger(__name__)

CLUSTDOCK_METADATA = "clustdock"
AFTER_END_METADATA = "clustdock.after_end"


class LibvirtConnexion(object):

    def __init__(self, host):
        """Create new libvirt connexion on the specified node"""
        self.host = host
        self.uri = None
        if self.host != 'localhost':
            self.uri = "qemu+ssh://%s/system" % self.host
        self.connect()
        _LOGGER.debug("new libvirt connexion on host '%s'", self.host)

    def connect(self):
        """Open a new connexion on the specified node"""
        try:
            self.cnx = libvirt.open(self.uri)
        except libvirt.libvirtError as exc:
            msg = "Couldn't connect to host '{}'\n".format(self.host)
            msg += str(exc)
            _LOGGER.error(msg)
            self.cnx = None

    def is_ok(self):
        """Check if the connexion is ok"""
        if self.cnx is None:
            return False
        return self.cnx.isAlive()

    def listvms(self, allnodes=True):
        """List all vms on the host"""
        vms = []
        try:
            domains = self.cnx.listAllDomains()
            for domain in domains:
                if not allnodes:
                    if domain.state()[0] != libvirt.VIR_DOMAIN_RUNNING:
                        continue
                node = LibvirtNode.from_domain(domain, self.host)
                vms.append(node)
        except libvirt.libvirtError:
            pass
        return vms

    @property
    def instance(self):
        if self.cnx is None:
          	self.connect()
        if not self.cnx.isAlive():
        	self.cnx.close()
        	self.connect()
        return self.cnx


class LibvirtNode(clustdock.VirtualNode):

    @classmethod
    def from_domain(cls, domain, host):
        """Create LibvirtNode from libvirt domain"""
        xmldom = domain.XMLDesc()
        tree = etree.fromstring(xmldom)
        source_path = get_source_path(tree)
        source_dir_path = os.path.dirname(source_path)
        name = domain.name()
        status = domain.state()[0]
        node = LibvirtNode(name, source_path, source_dir_path,
                           host=host, status=status,
                           img_path=source_path)
        return node

    def __init__(self, name, base_domain, storage_dir, **kwargs):
        """Instanciate a libvirt node"""
        super(LibvirtNode, self).__init__(name, **kwargs)
        self.base_domain = base_domain
        self.storage_dir = storage_dir
        self.mem = kwargs.get('mem', None)
        self.cpu = kwargs.get('cpu', None)
        self.status = kwargs.get('status', libvirt.VIR_DOMAIN_NOSTATE)
        if self.add_iface and not isinstance(self.add_iface, list):
            self.add_iface = [self.add_iface]
        self.img_path = kwargs.get('img_path', None)
        if self.img_path is None:
            self.new_img_path()

    def new_img_path(self):
        """Return path of the node image"""
        img_path = os.path.join(self.storage_dir, "%s.qcow2" % self.name)
        self.img_path = img_path
        return self.img_path

    def get_baseimg_path(self, xmldesc):
        """Get base image path from xml description"""
        tree = etree.fromstring(xmldesc)
        path = tree.xpath("//devices/disk/source/@file")[0]
        self.baseimg_path = path

    def getmetadata(self, domain):
        """Get clustdock metadata from given domain"""
        try:
            domain.metadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                                        CLUSTDOCK_METADATA)
        except libvirt.libvirtError:
            _LOGGER.error("Domain '%s' not spawned via clustdock", self.name)
            return
        try:
            after_end = domain.metadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                                     AFTER_END_METADATA)
            tree = etree.fromstring(after_end)
            self.after_end = tree.xpath("//after_end/@path")[0]
        except libvirt.libvirtError:
            _LOGGER.debug("no after_end hook set for domain '%s'", self.name)

    def start(self, pipe):
        """Start libvirt virtual machine"""
        spawned = 0
        msg = 'OK'
        _LOGGER.debug("Trying to spawn %s on host %s", self.name, self.host)
        mngtvirt = libvirt.open()
        cnx = LibvirtConnexion(self.host)
        # Check if base domain exists, otherwise exit
        base_dom = None
        try:
            base_dom = mngtvirt.lookupByName(self.base_domain)
        except libvirt.libvirtError as exc:
            msg = "Base image '{}' doesn't exist\n".format(self.base_domain)
            msg += str(exc)
            _LOGGER.error(msg)
            pipe.send(msg)
            sys.exit(1)
        # check if domain already exists
        if self.name in cnx.instance.listDefinedDomains():
            msg = "Image '{}' already exists. Skipping\n".format(self.name)
            # if force, delete and create
            _LOGGER.error(msg)
            pipe.send(msg)
            sys.exit(1)

        # Get xml description of the base image
        bxml_desc = base_dom.XMLDesc()
        # Change xml content
        new_xml = self.build_xml(bxml_desc)

        if self.before_start:
            _LOGGER.debug("Trying to launch before start hook: %s", self.before_start)
            rc, _, stderr = self.run_hook(self.before_start, clustdock.LIBVIRT_NODE)
            if rc != 0:
                msg = "Error when spawning '{}'\n".format(self.name)
                msg += stderr
                _LOGGER.error(msg)
                pipe.send(msg)
                sys.exit(1)

        # Create new disk file for the node
        # Just save diffs from based image
        cmd = "qemu-img create -f qcow2 -b %s %s && chmod a+w %s" % (self.baseimg_path,
                                                                     self.img_path,
                                                                     self.img_path)
        _LOGGER.debug("Launching %s", cmd)
        p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        (_, stderr) = p.communicate()
        if p.returncode != 0:
            msg = "Error when spawning '{}'\n".format(self.name)
            msg += stderr
            _LOGGER.error(msg)
            spawned = 1
            self.stop(cnx, fork=False)
        else:
            cmd = "virt-customize --hostname %s -a %s" % (self.name, self.img_path)
            # cmd = "guestfish -i -a %s write /etc/hostname '%s'" % (
            #      self.img_path,
            #      self.name)
            _LOGGER.debug("Launching %s", cmd)
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            (_, stderr) = p.communicate()
            if p.returncode != 0:
                msg = "Setting hostname for node '{}' failed\n".format(self.name)
                msg += stderr
                _LOGGER.error(msg)
                spawned = 1
                self.stop(cnx, fork=False)
            else:
                try:
                    cnx.instance.defineXML(new_xml)
                    dom = cnx.instance.lookupByName(self.name)

                    dom.setMetadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                                    "<clustdock/>", "clustdock", CLUSTDOCK_METADATA)
                    if self.after_end:
                        dom.setMetadata(libvirt.VIR_DOMAIN_METADATA_ELEMENT,
                                        "<after_end path='%s'/>" % self.after_end,
                                        "clustdock",
                                        AFTER_END_METADATA)

                    dom.create()
                    if self.after_start:
                        _LOGGER.debug("Trying to launch after start hook: %s",
                                      self.after_start)
                        rc, _, stderr = self.run_hook(self.after_start,
                                                      clustdock.LIBVIRT_NODE)
                        if rc != 0:
                            msg = "Error when spawning '{}'\n".format(self.name)
                            msg += stderr
                            _LOGGER.error(msg)
                            spawned = 1
                except libvirt.libvirtError as exc:
                    msg = "Domain '{}' alreay exists\n".format(self.name)
                    msg += str(exc)
                    _LOGGER.error(exc)
                    spawned = 1

        pipe.send(msg)
        cnx.instance.close()
        sys.exit(spawned)

    def stop(self, pipe=None, fork=True):
        """Stop libvirt node"""
        msg = 'OK'
        rc = 0
        cnx = LibvirtConnexion(self.host)
        try:
            dom = cnx.instance.lookupByName(self.name)
        except libvirt.libvirtError as exc:
            msg = "Couldn't find domain '{}'\n".format(self.name)
            msg += str(exc)
            _LOGGER.error(msg)
            rc = 1
        else:
            self.getmetadata(dom)
            if dom.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                _LOGGER.debug('Destroying domain %s', self.name)
                dom.destroy()
            _LOGGER.debug('Undefine domain %s', self.name)
            try:
                dom.undefine()  # --remove-all-storage
            except libvirt.libvirtError as exc:
                msg = "Cannot undefine domain '{}'\n".format(self.name)
                msg += str(exc)
                _LOGGER.error(msg)
                rc = 1
            else:
                if self.after_end:
                    _LOGGER.debug("Trying to launch after end hook: %s", self.after_end)
                    rc, _, stderr = self.run_hook(self.after_end, clustdock.LIBVIRT_NODE)
                    if rc != 0:
                        msg = "Error when stopping '{}'\n".format(self.name)
                        msg += stderr
                        _LOGGER.error(msg)
                        rc = 1
        cmd = "rm -f %s" % self.img_path
        _LOGGER.debug("Launching %s", cmd)
        p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        (_, stderr) = p.communicate()
        if p.returncode != 0:
            msg = "Error when removing disk for node '{}'\n".format(self.name)
            msg += stderr
            _LOGGER.error(msg)
            rc = 1
        cnx.instance.close()
        if fork:
            if pipe:
                pipe.send(msg)
            sys.exit(rc)
        else:
            return rc

    def get_ip(self):
        '''Get vm ip from domain name'''
        ip = ''
        cnx = LibvirtConnexion(self.host)
        try:
            domain = cnx.instance.lookupByName(self.name)
        except libvirt.libvirtError:
            _LOGGER.error("Couldn't find domain '{}'\n".format(self.name))
            cnx.instance.close()
            return ip
        xml_desc = domain.XMLDesc()
        tree = etree.fromstring(xml_desc)
        mac = tree.xpath("//mac/@address")[0]
        _LOGGER.debug('mac of domain %s is %s', self.name, mac)
        try:
            cmd = "ip neigh | grep '%s' | awk '{print $1}'" % mac
            p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
            (node_info, _) = p.communicate()
            ip = node_info.strip()
            _LOGGER.debug("ip of %s is '%s'", self.name, ip)

        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when getting ip of %s", self.name)
        self.ip = ip
        cnx.instance.close()
        return ip

    def build_xml(self, xml_info):
        '''Generate new XML description for the node from the base description'''
        tree = etree.fromstring(xml_info)
        dom = tree.xpath("/domain")[0]
        path = tree.xpath("//devices/disk/source")[0]
        self.baseimg_path = path.get('file')
        path.set('file', self.img_path)
        dom_name = tree.xpath("/domain/name")
        dom_name[0].text = self.name
        uuid = tree.xpath("/domain/uuid")[0]
        if etree.iselement(uuid):
            dom.remove(uuid)
        macs = tree.xpath("/domain/devices/interface/mac")
        for mac in macs:
            mac.getparent().remove(mac)
        if self.add_iface:
            for iface in self.add_iface:
                tree = self._add_iface(tree, iface)
        if self.mem:
            self._set_memory(tree)
        if self.cpu:
            self._set_cpu(tree)
        return etree.tostring(tree)

    def __str__(self):
        return self.name

    def __cmp__(self, node):
        if isinstance(node, clustdock.VirtualNode):
            return cmp(self.name, node.name)
        else:
            raise Exception("Cannot compare two object with different types")

    @staticmethod
    def _add_iface(tree, iface):
        """Add network interface to the VM"""
        desc = "<interface type='bridge'>\n" + \
               "  <source bridge='%s'/>\n" % iface + \
               "  <model type='virtio'/>\n" + \
               "</interface>\n"
        new_iface = etree.fromstring(desc)
        devices = tree.xpath("//devices")[0]
        devices.append(new_iface)
        return tree

    def _set_memory(self, tree):
        """Set memory limit for the node"""
        desc = "<memory unit='MB'>%s</memory>" % self.mem
        new_mem = etree.fromstring(desc)
        dom = tree.xpath("/domain")[0]
        cur_mem = tree.xpath("/domain/currentMemory")
        if cur_mem and etree.iselement(cur_mem[0]):
            dom.remove(cur_mem[0])
        memory = tree.xpath("/domain/memory")[0]
        dom.replace(memory, new_mem)
        return tree

    def _set_cpu(self, tree):
        """Set number of cpus for the node"""
        cpu = tree.xpath("/domain/vcpu")[0]
        cpu.text = str(self.cpu)
        return tree


def get_source_path(xmltree):
    """Get source image path from xml description"""
    path = xmltree.xpath("//devices/disk/source/@file")[0]
    return path
