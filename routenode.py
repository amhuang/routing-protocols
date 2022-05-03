import sys
import socket
import json
import time
import datetime
import threading
import math
import random

ROUTING_INTERVAL = 30
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class RouteNode:

    ########################## INITIALIZATION #########################

    def __init__(self): 
        self.neighbors = {}     # {port : cost}
        self.last = False
        self.sent = False
        self.cost_change = None
        self.routing = {}       # Routing table in format { port : [cost, next_hop], ... }
        self.most_recent = {}   # last distance vector received from each port

        self.topology = {}      # Topology of graph with link as keys and costs as values. Format { (lower_port, higher_port) : cost, ... }
        self.recvd = {}         # Packets received storerd as {seq num : origin port, ... }
        self.routing_computed = False

    def run(self): 
        if len(sys.argv) < 3:
            self.err_msg("Usage: python3 routenode.py dv <r/p> <update-interval> <local-port> <neighbor1-port> <cost-1> <neighbor2-port> <cost-2> ... [last] [<cost-change>]")
        
        self.algo = sys.argv[1]              # Algorithm to use (link state or distance vector)
        self.mode = sys.argv[2]              # Regular or Poisoned Reverse
        if sys.argv[3].isnumeric():
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
        if self.algo == "dv":
            for n in self.neighbors: 
                self.routing[n] = [self.neighbors[n], n]

            if self.mode == "r" or self.mode == "p":
                self.distance_vector()
            else:
                self.err_msg("Usage: Mode must be 'r' (regular) or 'p' (poisoned reverse)")
        
        elif self.algo == "ls":
            if self.mode != "r":
                self.err_msg("Usage: The link-state algorithm can only be run in regular mode, 'r'.")
            self.link_state()
        
        else:
            self.err_msg("Usage: Algorithm must be 'dv' or 'ls'.")

    def send_cost_change(self):
        # Update cost of neighbor with highest port num
        
        highest_port = max(self.neighbors)
        self.neighbors[highest_port] = self.cost_change
        print("[" + self.get_ts() + "]", "Node", highest_port, "cost updated to", self.cost_change)

        # Send cost update command message
        msg = ("COS\n" + str(self.cost_change) + "\n").encode()
        sock.sendto(msg, (self.ip, highest_port))
        print("[" + self.get_ts() + "]", "Link value message sent from Node", self.port, "to Node", highest_port)

        if self.algo == "dv":
            #self.routing[highest_port][0] = self.cost_change
            #self.print_routing()
            self.dv_cost_update(self.port, self.cost_change, receiver=highest_port) 
        
        elif self.algo == "ls":   # Redefine LSA
            self.make_lsa()
            self.ls_broadcast(self.lsa)

            # Update topology
            lower_port = self.port if self.port < highest_port else highest_port
            higher_port = highest_port if lower_port == self.port else self.port
            self.topology[(lower_port, higher_port)] = self.cost_change
            self.print_topology()

            # Recompute routing table
            self.compute_routing()

    def recv_cost_change(self, sender, cost):
        self.neighbors[sender] = cost
        print("[" + self.get_ts() + "]", "Node", sender, "cost updated to", cost)
        print("[" + self.get_ts() + "]", "Link value message received at Node", self.port, "from Node", sender)

        if self.algo == "dv":
            self.dv_cost_update(sender, cost) 
        
        elif self.algo == "ls":
            self.make_lsa()
            self.ls_broadcast(self.lsa)

            # Update topology
            lower_port = self.port if self.port < sender else sender
            higher_port = sender if self.port == lower_port else self.port
            self.topology[(lower_port, higher_port)] = cost
            self.print_topology()
            
            # Recompute routing table
            self.compute_routing()

    def make_lsa(self):
        self.seq = round(time.time(), 6)
        self.lsa = b"LSA\n" + str(self.port).encode() + b"\n" + json.dumps(self.neighbors).encode() + b"\n" + str(self.seq).encode()
        self.recvd[self.seq] = self.port

    ######################### LINK STATE ALGORITHM #######################

    def link_state(self):
        self.make_lsa()
        if self.last:
            self.sent = True
            self.ls_broadcast(self.lsa)
            self.ls_timers()

        recv_th = threading.Thread(target=self.ls_recv)
        recv_th.start()
    
    def ls_recv(self):
        global ROUTING_INTERVAL
        while True:
            # Receives routing table from addr
            pkt, addr = sock.recvfrom(2048)
            body = pkt.decode().split("\n")
            cmd = body[0]
            
            if cmd == "COS":
                sender = addr[1]
                cost = int(body[1])
                self.recv_cost_change(sender, cost)

            elif cmd == "LSA":
                origin = int(body[1])
                lsa = json.loads(body[2])
                seq = float(body[3])

                # convert keys of JSON from str to int
                dict_lsa = {}    
                for neighbor in lsa:
                    dict_lsa[int(neighbor)] = lsa[neighbor]

                # Identify duplicate LSAs received
                if seq in self.recvd and self.recvd[seq] == origin:
                    print("[" + self.get_ts() + "]", "DUPLICATE LSA packet received AND DROPPED:")
                    print("- LSA of node", origin)
                    print("- Sequence number", seq)
                    print("- Received from", addr[1])
                
                else:
                    # Propagate received LSA to neighbors
                    print("[" + self.get_ts() + "]", "LSA of Node", origin, "with sequence number", seq, "received from Node", addr[1])
                    self.update_topology(dict_lsa, origin, seq, addr[1])
                    self.ls_broadcast(pkt, addr[1])
                    self.recvd[seq] = origin
                    
                    # Propagate own LSA to neighbors if it hasn't already
                    if not self.sent:
                        self.sent = True
                        self.ls_broadcast(self.lsa)
                        self.ls_timers()
    
    def ls_broadcast(self, lsa, sender=None): 
        # lsa should be byte stream formatted with all LSA data
        for n in self.neighbors:
            if sender and sender == n:
                next

            print("[" + self.get_ts() + "]", "LSA of Node", self.port, "with sequence number", self.seq, "sent to Node", n)
            sock.sendto(lsa, (self.ip, n))

    def update_topology(self, dict_lsa, origin, seq, sender):
        # topology stored as list of tuples [(lower_port, higher_port, cost), ... ]   
        updated = False
        lsa = dict_lsa

        for neighbor in lsa:
            lower_port = origin if origin < neighbor else neighbor
            higher_port = origin if origin > neighbor else neighbor
            tup = (lower_port, higher_port) 

            # If edge not previously known or if edge value updated
            if tup not in self.topology or (tup in self.topology and self.topology[tup] != lsa[neighbor]):
                self.topology[tup] = lsa[neighbor]
                updated = True
        
        if updated:
            self.print_topology()
            if self.routing_computed:
                self.compute_routing()
    
    def print_topology(self):
        print("[" + self.get_ts() + "]", "Node", self.port, "Network Topology")
        
        sorted_keys = sorted(self.topology, key=lambda tup: (tup[0], tup[1]))
        for link in sorted_keys:
            print("- (" + str(self.topology[link]) + ")", "from Node", link[0], "to Node", link[1])
    
    # Starts and stops routing interval and update interval timers
    def ls_timers(self):
        global ROUTING_INTERVAL

        comp_routing = threading.Timer(ROUTING_INTERVAL, self.compute_routing)
        comp_routing.start()
        
        perp_update = threading.Thread(target=self.perpetual_update)
        perp_update.start()

        if self.cost_change:
            cost_change = threading.Timer(ROUTING_INTERVAL * 1.2, self.send_cost_change)
            cost_change.start()  

    # Create adjacency list from self.topology links
    def get_adj_table(self):
        adj = {}
        for link in self.topology:
            if link[0] not in adj:
                adj[link[0]] = []
            if link[1] not in adj:
                adj[link[1]] = []
            adj[link[0]].append((link[1], self.topology[link]))
            adj[link[1]].append((link[0], self.topology[link]))
        return adj

    def compute_routing(self): 
        '''
        DIJKSTRA'S ALGO
        Routing table in format { port : [cost, next_hop], ... }
        Topology in format { (lower_port, higher_port) : cost, ... }
        '''
        self.routing_computed = True
        adj = self.get_adj_table()
        
        # Initialization
        visited = { self.port }
        unvisited = set()
        for node in adj:
            if node != self.port:
                unvisited.add(node)

            if node in self.neighbors:
                self.routing[node] = [self.neighbors[node], node]
            elif node != self.port:
                self.routing[node] = [math.inf, None]

        # Loop
        while len(unvisited) > 0:
            min_node = min(unvisited, key=lambda x: self.routing[x][0])
            unvisited.remove(min_node)
            visited.add(min_node)

            min_neighbors = adj[min_node]
            for n in min_neighbors:
                neighbor = n[0]
                dist = n[1]
                
                if neighbor not in visited:
                    # dist to min unvisited node + edge between min_node and its neighbor
                    edge = (min_node, neighbor) if min_node < neighbor else (neighbor, min_node)
                    c = self.topology[edge]
                    alt_dist = self.routing[min_node][0] + c
                    
                    if alt_dist < self.routing[neighbor][0]:
                        # first hop to get to min_node
                        next_hop = self.routing[min_node][1]        
                        self.routing[neighbor] = [alt_dist, next_hop]

        self.print_routing()
        
    # Thread which sends the node's LSA out every self.update_interval
    def perpetual_update(self):
        while True:
            time.sleep(self.update_interval)
            self.ls_broadcast(self.lsa)

    ######################### DISTANCE VECTOR ######################

    def distance_vector(self):
        if self.last:
            self.sent = True
            self.dv_broadcast()
            if self.cost_change:
                t = threading.Timer(2.0, self.send_cost_change)
                t.start()
            self.print_routing()

        recv_th = threading.Thread(target=self.dv_recv)
        recv_th.start()
    
    def dv_broadcast(self):
        send_dv = self.routing.copy()
        table = b"TAB\n" + json.dumps(send_dv).encode() + b"\n"
        self.sent = True

        for n in self.neighbors:  
            if self.mode == "p":
                send_dv = self.routing.copy()
                for port in self.routing:
                    # if next hop to port is through n, poison the path back
                    if port != n and self.routing[port][1] == n:
                        send_dv[port][0] = math.inf

                table = b"TAB\n" + json.dumps(send_dv).encode() + b"\n"

            print("["+self.get_ts()+"]", "Message sent from Node", self.port, "to Node", n)
            sock.sendto(table, (self.ip, n))

    def dv_recv(self):
        while True:
            # Receives routing table from addr
            body, addr = sock.recvfrom(2048)
            body = body.decode().split("\n")

            if body[0] == "TAB":
                print("["+self.get_ts()+"]", "Message received at Node", self.port, "from Node", addr[1])
                table = json.loads(body[1])
                self.most_recent[addr[1]] = table
                self.dv_compute(table, addr)
            
            elif body[0] == "COS":  # Cost change control message
                sender = addr[1]
                cost = int(body[1])
                self.recv_cost_change(sender, cost)

    def dv_cost_update(self, sender, cost, receiver=None):
        # if the edge changed used to be part of the shortest path, change the distance vector
        updated = False

        if sender == self.port:
            for port in self.routing:
                # if the receiver end of the path change is the next hop for anything in the ruoting table
                next_hop = self.routing[port][1]
                if next_hop == receiver:
                    # see if another node has a faster path to the distination <port>
                    for past in self.most_recent:
                        if past != port and past in self.neighbors:
                            table = self.most_recent[past]
                            alt_dist = table[str(next_hop)][0] + self.routing[port][0]
                            if alt_dist < cost:
                                self.routing[port] = [alt_dist, past]
                                updated = True

        # if sender is an immediate neighbor
        elif self.routing[sender][1] == sender:
            for port in self.routing:
                # if the receiver end of the path change is the next hop for anything in the ruoting table
                next_hop = self.routing[port][1]
                if next_hop == sender:
                    # see if another node has a faster path to the distination <port>
                    potential_cost = self.routing[port][0] + cost
                    for past in self.most_recent:
                        if past != port and past in self.neighbors:
                            table = self.most_recent[past]
                            alt_dist = table[str(next_hop)][0] + self.routing[past][0]
                            
                            if updated and alt_dist < self.routing[port][0]:
                                self.routing[port] = [alt_dist, past]
                            elif alt_dist < potential_cost:
                                self.routing[port] = [alt_dist, past]
                                updated = True

        if updated:
            self.dv_broadcast()
            self.print_routing()
        return updated

    # Compute to change own DV based off table from addr
    def dv_compute(self, table, addr):
        sender = addr[1]
        c = self.routing[sender][0]  # distance between neighbor port and selfs
        updated = False

        for port in table:
            dist = c + table[port][0]
            port = int(port)
            
            if port != self.port:
                # if distance to port in new table is unknown
                if port not in self.routing:
                    self.routing[port] = [dist, sender]  # [dist to neighbor + neighbor's dist to port, neighbor's port]
                    updated = True

                # if a former path to the node is known
                elif port in self.routing:
                    # If direct path is shortest
                    if port in self.neighbors and self.neighbors[port] < dist and self.neighbors[port] < self.routing[port][0]:
                        self.routing[port] = [self.neighbors[port], port]
                        updated = True

                    # If a shorter non-direct path is found
                    elif dist < self.routing[port][0]: 
                        next_hop = self.routing[sender][1]   # next hop to get to sender
                        self.routing[port] = [dist, next_hop]
                        updated = True

                    # if the former shortest path got longer: the sender == next hop for a port in the table
                    elif port in self.neighbors and dist > self.routing[port][0] and sender == self.routing[port][1]:
                        # if the dist is shorter than the direct path
                        if dist < self.neighbors[port]:
                            self.routing[port] = [dist, sender] 
                        else:
                            self.routing[port] = [self.neighbors[port], port]
                        updated = True

        if updated or not self.sent:
            self.sent = True
            self.print_routing()
            self.dv_broadcast()
        return updated

    def print_routing(self):
        print("[" + self.get_ts() + "]", "Node", self.port, "Routing Table")
        sorted_keys = sorted(self.routing)

        for port in sorted_keys:
            dist = self.routing[port][0]
            next_hop = self.routing[port][1]
            
            if next_hop and next_hop != int(port):
                msg = "- (" + str(dist) + ") -> Node " + str(port) + "; Next hop -> Node " + str(next_hop)
            else: 
                msg = "- (" + str(dist) + ") -> Node " + str(port)
            print(msg)
    
    ######################### GENERAL FUNCTIONS ########################

    def get_ts(self):
        ts = str(round(time.time(), 3))
        if len(str(ts.split(".")[1])) < 3:
            ts += "0"
        return ts

    def err_msg(self, msg):
        print(msg)
        sys.exit(1)

    def validate_port(self, port):
        if int(port) < 1024 or 65535 < int(port):
            self.err_msg("Port numbers must be in the range 1024-65535.")

node = RouteNode()
node.run()