#!/usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
# Author : Antoine Sax <antoine.sax@bull.net>
# Contributors :
###############################################################################
# Copyright (C) 2018 Bull S.A.S.  -  All rights reserved
# Bull
# Rue Jean Jaurès
# B.P. 68
# 78340 Les Clayes-sous-Bois
# This is not Free or Open Source software.
# Please contact Bull S. A. S. for details about its license.
###############################################################################
'''Clustdock server testsuite'''

import unittest
import clustdock
import os
import clustdock.libvirt_node as lnode
import clustdock.server as server
import libvirt
from lxml import etree
from tempfile import mktemp


class LibvirtNodeTest(unittest.TestCase):

    def test_build_xml(self):
        '''Test the node xml definition'''

        dom = """<domain type="kvm" id="9">
  <name>00-START-BY-CLONING-ME</name>
  <uuid>81b20639-dba5-477e-a2da-07c88ad33f86</uuid>
  <memory unit="KiB">9194496</memory>
  <currentMemory unit="KiB">9194304</currentMemory>
  <vcpu placement="static">8</vcpu>
  <cpu mode="host-model">
    <model fallback="allow">SandyBridge</model>
    <vendor>Intel</vendor>
    <feature policy="require" name="pdpe1gb"/>
    <feature policy="require" name="ds"/>
    <feature policy="require" name="vme"/>
  </cpu>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2" cache="none"/>
      <source file="/mnt/vms/00-START-BY-CLONING-ME.img"/>
      <backingStore/>
      <target dev="vda" bus="virtio"/>
      <alias name="virtio-disk0"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x0"/>
    </disk>
    <interface type="bridge">
      <mac address="52:54:00:d1:e0:44"/>
      <source bridge="br0"/>
      <target dev="vnet0"/>
      <model type="virtio"/>
      <alias name="net0"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x0"/>
    </interface>
  </devices>
</domain>
"""
        expected_dom = """<domain type="kvm" id="9">
  <name>vnode0</name>
  <memory unit="KiB">9194496</memory>
  <currentMemory unit="KiB">9194304</currentMemory>
  <vcpu placement="static">8</vcpu>
  <cpu mode="host-model">
    <model fallback="allow">SandyBridge</model>
    <vendor>Intel</vendor>
    <feature policy="require" name="pdpe1gb"/>
    <feature policy="require" name="ds"/>
    <feature policy="require" name="vme"/>
  </cpu>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2" cache="none"/>
      <source file="/mnt/vms/vnode0.qcow2"/>
      <backingStore/>
      <target dev="vda" bus="virtio"/>
      <alias name="virtio-disk0"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x0"/>
    </disk>
    <interface type="bridge">
      <source bridge="br0"/>
      <target dev="vnet0"/>
      <model type="virtio"/>
      <alias name="net0"/>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x0"/>
    </interface>
  </devices>
</domain>"""
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME", "/mnt/vms")
        new_dom = node.build_xml(dom)
        self.assertEqual(new_dom, expected_dom)

    def test_build_xml_add_iface(self):
        '''Test the node xml definition'''

        dom = """
<domain type="kvm" id="9">
<name>00-START-BY-CLONING-ME</name>
<uuid>81b20639-dba5-477e-a2da-07c88ad33f86</uuid>
<memory unit="KiB">9194496</memory>
<currentMemory unit="KiB">9194304</currentMemory>
<vcpu placement="static">8</vcpu>
<cpu mode="host-model">
<model fallback="allow">SandyBridge</model>
<vendor>Intel</vendor>
<feature policy="require" name="pdpe1gb"/>
<feature policy="require" name="ds"/>
<feature policy="require" name="vme"/>
</cpu>
<devices>
<emulator>/usr/bin/qemu-system-x86_64</emulator>
<disk type="file" device="disk">
<driver name="qemu" type="qcow2" cache="none"/>
<source file="/mnt/vms/00-START-BY-CLONING-ME.img"/>
<backingStore/>
<target dev="vda" bus="virtio"/>
<alias name="virtio-disk0"/>
<address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x0"/>
</disk>
<interface type="bridge">
<mac address="52:54:00:d1:e0:44"/>
<source bridge="br0"/>
<target dev="vnet0"/>
<model type="virtio"/>
<alias name="net0"/>
<address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x0"/>
</interface>
</devices>
</domain>
"""
        expected_dom = """<domain type="kvm" id="9">
<name>vnode0</name>
<memory unit="KiB">9194496</memory>
<currentMemory unit="KiB">9194304</currentMemory>
<vcpu placement="static">8</vcpu>
<cpu mode="host-model">
<model fallback="allow">SandyBridge</model>
<vendor>Intel</vendor>
<feature policy="require" name="pdpe1gb"/>
<feature policy="require" name="ds"/>
<feature policy="require" name="vme"/>
</cpu>
<devices>
<emulator>/usr/bin/qemu-system-x86_64</emulator>
<disk type="file" device="disk">
<driver name="qemu" type="qcow2" cache="none"/>
<source file="/mnt/vms/vnode0.qcow2"/>
<backingStore/>
<target dev="vda" bus="virtio"/>
<alias name="virtio-disk0"/>
<address type="pci" domain="0x0000" bus="0x00" slot="0x03" function="0x0"/>
</disk>
<interface type="bridge">
<source bridge="br0"/>
<target dev="vnet0"/>
<model type="virtio"/>
<alias name="net0"/>
<address type="pci" domain="0x0000" bus="0x00" slot="0x02" function="0x0"/>
</interface>
<interface type="bridge">
  <source bridge="brama0"/>
  <model type="virtio"/>
</interface></devices>
</domain>"""
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME", 
                                 "/mnt/vms", add_iface="brama0")
        new_dom = node.build_xml(dom)
        self.assertEqual(new_dom, expected_dom)

    def test_set_memory(self):
        '''Test the memory setting'''
        
        dom = """<domain type='kvm' id='9'>
  <name>vnode0</name>
  <uuid>81b20639-dba5-477e-a2da-07c88ad33f86</uuid>
  <memory unit='KiB'>9194496</memory>
  <currentMemory unit='KiB'>9194304</currentMemory>
  <vcpu placement='static'>8</vcpu>
  <cpu mode='host-model'>
    <model fallback='allow'>SandyBridge</model>
    <vendor>Intel</vendor>
    <feature policy='require' name='pdpe1gb'/>
    <feature policy='require' name='ds'/>
    <feature policy='require' name='vme'/>
  </cpu>
</domain>
"""
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME", 
                                 "/mnt/vms", mem="8192")
        tree = etree.fromstring(dom)
        new_tree = node._set_memory(tree)
        new_dom = etree.tostring(new_tree)
        self.assertNotIn("<memory unit='KiB'>9194496</memory>", new_dom)
        self.assertNotIn("<currentMemory unit='KiB'>9194304</currentMemory>", new_dom)
        self.assertIn('<memory unit="MB">8192</memory>', new_dom)
    
    def test_set_memory_no_current(self):
        '''Test the memory setting without currentMemory field'''
        
        dom = """<domain type='kvm' id='9'>
  <name>vnode0</name>
  <uuid>81b20639-dba5-477e-a2da-07c88ad33f86</uuid>
  <memory unit='KiB'>9194496</memory>
  <vcpu placement='static'>8</vcpu>
  <cpu mode='host-model'>
    <model fallback='allow'>SandyBridge</model>
    <vendor>Intel</vendor>
    <feature policy='require' name='pdpe1gb'/>
    <feature policy='require' name='ds'/>
    <feature policy='require' name='vme'/>
  </cpu>
</domain>
"""
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME",
        "/mnt/vms", mem="8192")
        tree = etree.fromstring(dom)
        new_tree = node._set_memory(tree)
        new_dom = etree.tostring(new_tree)
        self.assertNotIn("<memory unit='KiB'>9194496</memory>", new_dom)
        self.assertIn('<memory unit="MB">8192</memory>', new_dom)
    
    def test_set_cpus(self):
        '''Test the cpu setting'''
        
        dom = """<domain type='kvm' id='9'>
  <name>vnode0</name>
  <uuid>81b20639-dba5-477e-a2da-07c88ad33f86</uuid>
  <memory unit='KiB'>9194496</memory>
  <currentMemory unit='KiB'>9194304</currentMemory>
  <vcpu placement='static'>8</vcpu>
  <cpu mode='host-model'>
    <model fallback='allow'>SandyBridge</model>
    <vendor>Intel</vendor>
    <feature policy='require' name='pdpe1gb'/>
    <feature policy='require' name='ds'/>
    <feature policy='require' name='vme'/>
  </cpu>
</domain>
"""
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME",
                                 "/mnt/vms", cpu=2)
        tree = etree.fromstring(dom)
        new_tree = node._set_cpu(tree)
        new_dom = etree.tostring(new_tree)
        self.assertNotIn('<vcpu placement="static">8</vcpu>', new_dom)
        self.assertIn('<vcpu placement="static">2</vcpu>', new_dom)

    def test_encode_decode_libvirt_node(self):
        """Test encoding/decoding of libvirt node"""
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME",
                                 "/mnt/vms")
        node_desc = server.encode_node(node)
        expected = {'base_domain': '00-START-BY-CLONING-ME',
                    'clustername': 'vnode',
                    'before_start': None,
                    'after_start': None,
                    'after_end': None,
                    'cpu': None,
                    'host': 'localhost',
                    'idx': 0,
                    'img_path': '/mnt/vms/vnode0.qcow2',
                    'storage_dir': '/mnt/vms',
                    'ip': '',
                    'mem': None,
                    'name': 'vnode0',
                    'add_iface': None,
                    'status': libvirt.VIR_DOMAIN_NOSTATE
                    }
        self.assertDictEqual(expected, node_desc)
        new_node = server.decode_node(node_desc)
        self.assertEqual(node, new_node)

    def test_run_hook_libvirt(self):
        """Test run hook for libvirt node"""

        content = """#!/bin/bash
echo -n "$1 $2 $3"
"""
        tmpfile = mktemp(prefix="clustdock-hook-")
        with open(tmpfile, 'w') as myfile:
            myfile.write(content)
        node = lnode.LibvirtNode("vnode0", "00-START-BY-CLONING-ME",
                                 "/mnt/vms")
        rc, stdout, stderr = node.run_hook(tmpfile, clustdock.LIBVIRT_NODE)
        self.assertEqual(rc, 126)
        self.assertEqual(stdout, "")
        self.assertIn("Permission denied", stderr)
        os.chmod(tmpfile, 0755)
        rc, stdout, stderr = node.run_hook(tmpfile, clustdock.LIBVIRT_NODE)
        self.assertEqual(rc, 0)
        self.assertEqual("%s %s %s" % (node.name,
                                       clustdock.LIBVIRT_NODE,
                                       node.host), stdout)
        self.assertEqual("", stderr)
        self.remove_file(tmpfile)

    def remove_file(self, path):
        """Remove temporary file"""
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

if __name__ == "__main__":
    unittest.main()
