import sys
import socket
import json
import time
import datetime
import threading
import math
import random

ROUTING_INTERVAL = 2
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class RouteNode:

    ########################## INITIALIZATION #########################

    def __init__(self): 
        self.neighbors = {}     # {port : cost}
        self.last = False
        self.sent = False
        self.cost_change = None
        self.dv = {}            # distance vector in format { port : [cost, next_hop] }
        self.most_recent = {}   # last distance vector received from each port
        self.topology = {}
        self.recvd = {}         # Packets received storerd as {seq num : origin port}
        self.routing = {}
        self.activated = False

    def run(self): 
        if len(sys.argv) < 3:
            self.err_msg("Usage: python3 routenode.py dv <r/p> <update-interval> <local-port> <neighbor1-port> <cost-1> <neighbor2-port> <cost-2> ... [last] [<cost-change>]")
        
        algo = sys.argv[1]              # Algorithm to use (link state or distance vector)
        mode = sys.argv[2]              # Regular or Poisoned Reverse
        self.update_interval = int(sys.argv[3]) + random.uniform(0,1)   # for link state 
        self.port = int(sys.argv[4])    # Local port
        self.ip = "127.0.0.1"
        self.validate_port(self.port)

        i = 5
        while i < len(sys.argv) - 1 and sys.argv[i] != "last":
            port = int(sys.argv[i])
            self.validate_port(port)
            cost = int(sys.argv[i + 1])
            self.neighbors[port] = cost
            i += 2

        if i < len(sys.argv) and sys.argv[i] == "last":
            self.last = True
            i += 1
        if i < len(sys.argv):
            self.cost_change = int(sys.argv[i])

        sock.bind((self.ip, self.port))    # socket listening
        
        # run distance vector algorithm
        if algo == "dv":
            for n in self.neighbors: 
                self.dv[n] = [self.neighbors[n], n]

            if mode == "r" or mode == "p":
                self.mode = mode
                self.distance_vector()
            else:
                self.err_msg("Usage: Mode must be 'r' (regular) or 'p' (poisoned reverse)")
        
        elif algo == "ls":
            if mode != "r":
                self.err_msg("Usage: The link-state algorithm can only be run in regular mode, 'r'.")
            self.link_state()
        
        else:
            self.err_msg("Usage: Algorithm must be 'dv' or 'ls'.")

    ####################### LINK STATE ALGORITHM ######################

    def link_state(self):
        self.seq = str(round(time.time(), 3))
        self.lsa = b"LSA\n" + str(self.port).encode() + b"\n" +  json.dumps(self.neighbors).encode() + b"\n" + self.seq.encode() + b"\n"
        
        if self.last:
            self.sent = True
            self.ls_broadcast(self.lsa)
        
        recv_th = threading.Thread(target=self.ls_recv)
        recv_th.start()
    
    def ls_recv(self):
        while True:
            # Receives routing table from addr
            content, addr = sock.recvfrom(2048)
            body = content.decode().split("\n")
            origin = int(body[1])
            unproc_lsa = json.loads(body[2])
            seq = float(body[3])
            lsa = {}

            for neighbor in unproc_lsa:    # convert keys of JSON to int
                lsa[int(neighbor)] = unproc_lsa[neighbor]

            ts = str(round(time.time(), 3))
            if seq in self.recvd and self.recvd[seq] == origin:
                print("[" + ts + "]", "DUPLICATE LSA packet received AND DROPPED:")
                print("- LSA of node", origin)
                print("- Sequence number", seq)
                print("- Received from", addr[1])
            else:
                self.recvd[seq] = origin
                print("[" + ts + "]", "LSA of node", origin, "with sequence number", seq, "received from Node", addr[1])
                self.update_topology(lsa, origin, seq, addr[1])
                self.propagate_lsa(content, addr[1])
                if not self.activated:
                    self.activated = True
                    self.ls_broadcast(self.lsa)
        
    def ls_broadcast(self, lsa): 
        self.sent = True

        for n in self.neighbors:  
            ts = str(round(time.time(), 3))
            print("[" + ts + "]", "LSA of Node", self.port, "with sequence number", self.seq, "sent to Node", n)
            sock.sendto(lsa, (self.ip, n))

    def update_topology(self, lsa, origin, seq, sender):
        # topology stored as list of tuples [(lower_port, higher_port, cost), ... ]   
        updated = False
        for neighbor in lsa:
            lower_port = origin if origin < neighbor else neighbor
            higher_port = origin if origin > neighbor else neighbor
            tup = (lower_port, higher_port) 
            if tup not in self.topology:
                self.topology[tup] = lsa[neighbor]
                updated = True
        
        if updated:
            self.print_topology()
    
    def print_topology(self):
        ts = str(round(time.time(), 3))
        print("[" + ts + "]", "Node", self.port, "Network Topology")
        
        sorted_keys = sorted(self.topology, key=lambda tup: (tup[0], tup[1]))
        for link in sorted_keys:
            print("- (" + str(self.topology[link]) + ")", "from Node", link[0], "to Node", link[1])

    def propagate_lsa(self, content, sender):
        # Content should be byte stream formatted with all LSA data
        for n in self.neighbors:
            if n != sender:
                sock.sendto(content, (self.ip, n))

    ######################### DISTANCE VECTOR ######################

    def distance_vector(self):
        if self.last:
            self.sent = True
            self.dv_broadcast()
            if self.cost_change:
                t = threading.Timer(2.0, self.send_cost_change)
                t.start()

        recv_th = threading.Thread(target=self.dv_recv)
        recv_th.start()
    
    def send_cost_change(self):
        highest_port = max(self.dv)
        self.neighbors[highest_port] = self.cost_change

        self.dv[highest_port][0] = self.cost_change
        ts = str(round(time.time(), 3))
        print("[" + ts + "]", "Node", highest_port, "cost updated to", self.cost_change)
        
        msg = ("COS\n" + str(self.cost_change) + "\n").encode()
        sock.sendto(msg, (self.ip, highest_port))
        print("[" + ts + "]", "Link value message sent from Node", self.port, "to Node", highest_port)

    def dv_broadcast(self):
        send_dv = self.dv.copy()
        table = b"TAB\n" + json.dumps(send_dv).encode() + b"\n"
        self.sent = True

        for n in self.neighbors:  
            if self.mode == "p":
                send_dv = self.dv.copy()
                for port in self.dv:
                    # if next hop to port is through n, poison the path back
                    if port != n and self.dv[port][1] == n:
                        send_dv[port][0] = math.inf

                table = b"TAB\n" + json.dumps(send_dv).encode() + b"\n"

            print("Message sent from Node", self.port, "to Node", n)
            sock.sendto(table, (self.ip, n))

    def dv_recv(self):
        while True:
            # Receives routing table from addr
            body, addr = sock.recvfrom(2048)
            body = body.decode().split("\n")

            i = 0
            while i < len(body):
                if body[i] == "TAB":
                    i += 1
                    table = json.loads(body[i])
                    self.dv_compute(table, addr)
                    self.most_recent[addr[1]] = table
                    print("Message received at Node", self.port, "from Node", addr[1])
                
                elif body[i] == "COS":  # Cost change control message
                    i += 1
                    sender = addr[1]
                    cost = int(body[i])
                    self.neighbors[sender] = cost

                    ts = str(round(time.time(), 3))
                    print("[" + ts + "]", "Node", sender, "cost updated to", cost)
                    print("[" + ts + "]", "Link value message received at Node", self.port, "from Node", sender)
        
                    self.cost_update(sender, cost) 
                i += 1

    def cost_update(self, sender, cost):
        # if the edge changed used to be part of the shortest path, change the distance vector
        updated = False

        # if sender is an immediate neighbor
        if self.dv[sender][1] == sender:
            for port in self.most_recent:
                if port != sender:
                    # if most recent table received says there's a shorter way to Y, loop through most recent tables received
                    table = self.most_recent[port]

                    # most recent distance of neighbor to update sender + distance to neighbor
                    alt_dist = table[str(sender)][0] + self.dv[port][0]
                    if alt_dist < cost:
                        self.dv[sender] = [alt_dist, port]
                        updated = True
                    else: 
                        self.dv[sender] = [cost, sender]
                        updated = True

        if updated:
            self.dv_broadcast()
            self.print_routing(self.dv)
        return updated
            
    # Compute to change own DV based off table from addr
    def dv_compute(self, table, addr):
        sender = addr[1]
        c = self.dv[sender][0]  # distance between neighbor port and selfs
        updated = False
        #print("  Received table from", addr,":",table)

        for port in table:
            dist = c + table[port][0]
            port = int(port)
            
            if port != self.port:
                # if distance to port in new table is unknown
                if port not in self.dv:
                    self.dv[port] = [dist, sender]  # s[dist to neighbor + neighbor's dist to port, neighbor's port]
                    updated = True

                # if a former path to the node is known
                elif port in self.dv:
                    # If direct path is shortest
                    if port in self.neighbors and self.neighbors[port] < dist and self.neighbors[port] < self.dv[port][0]:
                        self.dv[port] = [self.neighbors[port], port]
                        updated = True

                    # If a shorter non-direct path is found
                    elif dist < self.dv[port][0]: 
                        next_hop = self.dv[sender][1]   # next hop to get to sender
                        self.dv[port] = [dist, next_hop]
                        updated = True

                    # if the former shortest path got longer: the sender == next hop for a port in the table
                    elif dist > self.dv[port][0] and sender == self.dv[port][1]:
                        if dist < self.neighbors[port]:
                            self.dv[port] = [dist, sender] 
                        else:
                            self.dv[port] = [self.neighbors[port], port]
                        updated = True

        if updated or not self.sent:
            self.sent = True
            self.print_routing(self.dv)
            self.dv_broadcast()
        return updated

    def print_routing(self, table):
        ts = str(round(time.time(), 3))   #datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
        print("[" + ts + "]", "Node", self.port, "Routing Table")
        sorted_keys = sorted(table)

        for port in sorted_keys:
            dist = table[port][0]
            next_hop = table[port][1]
            
            if next_hop and next_hop != int(port):
                msg = "- (" + str(dist) + ") -> Node " + str(port) + "; Next hop -> Node " + str(next_hop)
            else: 
                msg = "- (" + str(dist) + ") -> Node " + str(port)
            print(msg)
    
    ######################### GENERAL FUNCTIONS ########################
    
    def err_msg(self, msg):
        print(msg)
        sys.exit(1)

    def validate_port(self, port):
        if int(port) < 1024 or 65535 < int(port):
            self.err_msg("Port numbers must be in the range 1024-65535.")

node = RouteNode()
node.run()