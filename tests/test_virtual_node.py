#!/usr/bin/env python
# -*- coding: utf-8 -*-
###############################################################################
# Author : Antoine Sax <antoine.sax@bull.net>
# Contributors :
###############################################################################
# Copyright (C) 2015  Bull S.A.S.  -  All rights reserved
# Bull
# Rue Jean Jaurès
# B.P. 68
# 78340 Les Clayes-sous-Bois
# This is not Free or Open Source software.
# Please contact Bull SAS for details about its license.
###############################################################################
'''Clustdock server testsuite'''

import unittest
import clustdock
import clustdock.server as server
import clustdock.virtual_cluster as vc


class VirtualNodeTest(unittest.TestCase):
    """Testing function of VirtualNode class"""

    def test_split_name(self):
        '''Test split name'''

        name = "allletters0"
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "allletters")
        self.assertEqual(idx, 0)

        name = "thename223"
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "thename")
        self.assertEqual(idx, 223)

        name = "node-name0"
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "node-name")
        self.assertEqual(idx, 0)

        name = "node_name0"
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "node_name")
        self.assertEqual(idx, 0)

        name = "node.name0"
        self.assertRaises(AttributeError, clustdock.VirtualNode.split_name, name)

        name = "-nodename0"
        self.assertRaises(AttributeError, clustdock.VirtualNode.split_name, name)

        name = "_nodename0"
        self.assertRaises(AttributeError, clustdock.VirtualNode.split_name, name)


class VirtualClusterTest(unittest.TestCase):
    """Testing function of VirtualCluster class"""

    def test_valid_cluster_name(self):
        '''Test valid cluster name'''

        name = "onlyminusletters"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))
        name = "node-name"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))
        name = "node_name"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))
        name = "n-"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))
        name = "n_"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))
        name = "n--"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))
        name = "n__"
        self.assertTrue(vc.VirtualCluster.valid_clustername(name))

        name = "notonlyMINUSletters"
        self.assertFalse(vc.VirtualCluster.valid_clustername(name))
        name = "notonlyletters0123"
        self.assertFalse(vc.VirtualCluster.valid_clustername(name))
        name = "node.with.dot"
        self.assertFalse(vc.VirtualCluster.valid_clustername(name))
        name = "-beginwithdash"
        self.assertFalse(vc.VirtualCluster.valid_clustername(name))
        name = "_beginwithunderscore"
        self.assertFalse(vc.VirtualCluster.valid_clustername(name))
        name = "with1number2in3the4name"
        self.assertFalse(vc.VirtualCluster.valid_clustername(name))

    def test_virtual_cluster_encode_decode(self):
        """Test Encoding/Decoding virtual cluster"""
        profil = {
            'vtype': "libvirt",
            'img': "bxifmfvt",
            'img_dir': "/var/lib/libvirt/images",
            'mem': 1024,
            'cpu': 1
        }
        name = "cluster_name"
        cluster = vc.VirtualCluster(name, 'gama', profil)
        expected = {
            'cfg': {
                'default': {
                    'cpu': 1,
                    'img': 'bxifmfvt',
                    'img_dir': '/var/lib/libvirt/images',
                    'mem': 1024,
                    'vtype': 'libvirt'
                }
            },
            'name': 'cluster_name',
            'profil': 'gama',
            'nodes': {}
        }
        cluster_desc = server.encode_cluster(cluster)
        self.assertDictEqual(expected, cluster_desc)
        new_cluster = server.decode_cluster(cluster_desc)
        self.assertDictEqual(new_cluster.__dict__, expected)

    def test_virtual_cluster_encode_decode_with_nodes(self):
        """Test Encoding/Decoding virtual cluster with nodes"""
        profil = {
            'vtype': "libvirt",
            'img': "bxifmfvt",
            'img_dir': "/var/lib/libvirt/images",
            'mem': 1024,
            'cpu': 1
        }
        name = "cluster_name"
        cluster = vc.VirtualCluster(name, 'gama', profil)
        cluster.add_node(1, None)
        cluster_desc = server.encode_cluster(cluster)
        expected = {
            'cfg': {
                'default': {
                    'cpu': 1,
                    'host': None,
                    'img': 'bxifmfvt',
                    'img_dir': '/var/lib/libvirt/images',
                    'mem': 1024,
                    'vtype': 'libvirt'
                }
            },
            'name': 'cluster_name',
            'profil': 'gama',
            'nodes': {
                'cluster_name1': {
                    'clustername': 'cluster_name',
                    'cpu': 1,
                    'host': 'localhost',
                    'idx': 1,
                    'img': 'bxifmfvt',
                    'img_dir': '/var/lib/libvirt/images',
                    'ip': '',
                    'mem': 1024,
                    'name': 'cluster_name1',
                    'supl_iface': None,
                    'unreachable': False,
                    'uri': None
                }
            }
        }
        self.maxDiff = None
        self.assertDictEqual(expected, cluster_desc)
        new_cluster = server.decode_cluster(cluster_desc)
        encoded = server.encode_cluster(new_cluster)
        self.assertDictEqual(encoded, expected)


if __name__ == "__main__":
    unittest.main()
