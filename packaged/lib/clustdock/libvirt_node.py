# -*- coding: utf-8 -*-
'''
@author Antoine Sax <antoine.sax@atos.net>
@copyright 2015  Bull S.A.S.  -  All rights reserved.\n
           This is not Free or Open Source software.\n
           Please contact Bull SAS for details about its license.\n
           Bull - Rue Jean Jaurès - B.P. 68 - 78340 Les Clayes-sous-Bois
@file clustdock/libvirt_node.py
@namespace clustdock.libvirt_node LibvirtNode definition
'''
import logging
import sys
import os
import subprocess as sp
from lxml import etree
import time
import libvirt
import clustdock

_LOGGER = logging.getLogger(__name__)


class LibvirtNode(clustdock.VirtualNode):

    def __init__(self, name, img, img_dir, **kwargs):
        """Instanciate a libvirt node"""
        super(LibvirtNode, self).__init__(name, **kwargs)
        self.uri = "qemu+ssh://%s/system" % self.host if self.host != 'localhost' else None
        self.img = img
        self.img_dir = img_dir
        self.mem = kwargs.get('mem', None)
        self.cpu = kwargs.get('cpu', None)
        if self.add_iface and not isinstance(self.add_iface, list):
            self.add_iface = [self.add_iface]

    @property
    def img_path(self):
        """Return path of the node image"""
        return os.path.join(self.img_dir, "%s.qcow2" % self.name)

    def get_baseimg_path(self, xmldesc):
        """Get base image path from xml description"""
        tree = etree.fromstring(xmldesc)
        path = tree.xpath("//devices/disk/source/@file")[0]
        self.baseimg_path = path

    def start(self, pipe):
        """Start libvirt virtual machine"""
        spawned = 0
        msg = 'OK'
        _LOGGER.debug("Trying to spawn %s on host %s", self.name, self.host)
        try:
            cvirt = libvirt.open(self.uri)
        except libvirt.libvirtError as exc:
            msg = "Couldn't connect to host '{}'\n".format(self.host)
            msg += str(exc)
            _LOGGER.error(msg)
            pipe.send(msg)
            sys.exit(1)
        mngtvirt = libvirt.open()
        # Check if base domain exists, otherwise exit
        base_dom = None
        try:
            base_dom = mngtvirt.lookupByName(self.img)
        except libvirt.libvirtError as exc:
            msg = "Base image '{}' doesn't exist\n".format(self.img)
            msg += str(exc)
            _LOGGER.error(msg)
            pipe.send(msg)
            sys.exit(1)
        # check if domain already exists
        if self.name in cvirt.listDefinedDomains():
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
            self.stop(fork=False)
        else:
            # cmd = "virt-customize --hostname %s -a %s" % (self.name, self.img_path)
            cmd = "guestfish -i -a %s write /etc/hostname '%s'" % (
                  self.img_path,
                  self.name)
            _LOGGER.debug("Launching %s", cmd)
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            (_, stderr) = p.communicate()
            if p.returncode != 0:
                msg = "Setting hostname for node '{}' failed\n".format(self.name)
                msg += stderr
                _LOGGER.error(msg)
                spawned = 1
                self.stop(fork=False)
            else:
                try:
                    cvirt.defineXML(new_xml)
                    dom = cvirt.lookupByName(self.name)
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
        sys.exit(spawned)

    def stop(self, pipe=None, fork=True):
        """Stop libvirt node"""
        msg = 'OK'
        rc = 0
        try:
            cvirt = libvirt.open(self.uri)
        except libvirt.libvirtError as exc:
            msg = "Couldn't connect to host '{}'\n".format(self.host)
            msg += str(exc)
            _LOGGER.error(msg)
            rc = 1
        else:
            dom_list = cvirt.listAllDomains()
            dom = cvirt.lookupByName(self.name)
            if dom.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                _LOGGER.debug('Destroying domain %s', self.name)
                dom.destroy()
            _LOGGER.debug('Undefine domain %s', self.name)
            dom.undefine()  # --remove-all-storage
            cmd = "rm -f %s" % self.img_path
            _LOGGER.debug("Launching %s", cmd)
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
            (_, stderr) = p.communicate()
            if p.returncode != 0:
                msg = "Error when removing disk for node '{}'\n".format(self.name)
                msg += stderr
                _LOGGER.error(msg)
                rc = 1
            else:
                _LOGGER.debug("Trying to launch after end hook: %s", self.after_end)
                rc, _, stderr = self.run_hook(self.after_end, clustdock.LIBVIRT_NODE)
                if rc != 0:
                    msg = "Error when stopping '{}'\n".format(self.name)
                    msg += stderr
                    _LOGGER.error(msg)
                    rc = 1
        if fork:
            if pipe:
                pipe.send(msg)
            sys.exit(rc)
        else:
            return rc

    def is_alive(self):
        """Return True if node is still present on the host, else False"""
        res = False
        try:
            cvirt = libvirt.open(self.uri)
            domain = cvirt.lookupByName(self.name)
            res = True
            self.running = domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING
        except libvirt.libvirtError:
            pass
        return res

    def get_ip(self):
        '''Get vm ip from domain name'''
        if self.ip != '':
            return self.ip
        ip = ''
        if not self.is_alive():
            return None
        cvirt = libvirt.open(self.uri)
        domain = cvirt.lookupByName(self.name)
        xml_desc = domain.XMLDesc()
        tree = etree.fromstring(xml_desc)
        mac = tree.xpath("//mac/@address")[0]
        _LOGGER.debug('mac of domain %s is %s', self.name, mac)
        try:
            cmd = "ip neigh | grep '%s' | awk '{print $1}'" % mac
            for retry in range(0, 20):
                p = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
                (node_info, _) = p.communicate()
                ip = node_info.strip()
                if ip == '':
                    _LOGGER.debug("ip of %s is empty, retrying", self.name)
                    time.sleep(2)
                else:
                    _LOGGER.debug("ip of %s is %s", self.name, ip)
                    break

        except sp.CalledProcessError:
            _LOGGER.error("Something went wrong when getting ip of %s", self.name)
        self.ip = ip
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
