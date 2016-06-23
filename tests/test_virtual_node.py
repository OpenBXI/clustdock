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
import libvirt


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
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "node.name0")
        self.assertEqual(idx, None)

        name = "-nodename0"
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "-nodename0")
        self.assertEqual(idx, None)

        name = "_nodename0"
        nodename, idx = clustdock.VirtualNode.split_name(name)
        self.assertEqual(nodename, "_nodename0")
        self.assertEqual(idx, None)


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


if __name__ == "__main__":
    unittest.main()
